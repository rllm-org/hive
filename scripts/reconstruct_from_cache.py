#!/usr/bin/env python3
"""Reconstruct Hive DB from local GitHub cache (scripts/github_cache.json)."""

import json
import os
import re

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")
CACHE_FILE = "scripts/github_cache.json"
SKIP_MESSAGES = {"initial task upload", "Initial commit", "Add README"}

SCORE_PATTERNS = [
    # Explicit score labels
    re.compile(r'score[:\s=~]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'scored\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'accuracy[:\s]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*(?:score(?!d)|accuracy)\b', re.IGNORECASE),
    # Unit-tagged scores (require non-negative context)
    re.compile(r'(?<![−\-])(\d+\.?\d*)\s*ELO\b(?!\s*anchor)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*AUC\b', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*mpps', re.IGNORECASE),
    # Score-reporting verbs/phrases
    re.compile(r'improved to\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'best at\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'new best\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'best run[:\s]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'^eval run\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'^final eval run\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*NEW\s*(GLOBAL\s*)?BEST', re.IGNORECASE),
    # "record XXXX.X" — only match decimals (not "record IIR baseline")
    re.compile(r'\brecord\s+(\d+\.\d+)', re.IGNORECASE),
    # Parenthesized scores: (2918.2 baseline), (2918.2 ELO)
    re.compile(r'\((\d+\.?\d*)\s*(?:baseline|elo)\b', re.IGNORECASE),
    # "adopt agent 0.400" or "adopt agent's 0.74 code"
    re.compile(r'adopt\s+\S+\s+(\d+\.\d+)', re.IGNORECASE),
    re.compile(r"adopt\s+\S+'s\s+(\d+\.\d+)", re.IGNORECASE),
    # "eval: 0.300 (6/20)" or "V7b final: 0.150 (3/20)"
    re.compile(r':\s*(\d+\.\d+)\s*\(\d+/\d+\)', re.IGNORECASE),
    # "exp10 rerun: NEW BEST 0.75!"
    re.compile(r'NEW\s+BEST\s+(\d+\.?\d*)', re.IGNORECASE),
    # "exp12 rerun2: 0.74 with airline"
    re.compile(r'rerun\d*:\s*(\d+\.\d+)', re.IGNORECASE),
    # "V7 Daytona: 0.200" — but NOT "V3 code" or version refs
    re.compile(r'V\d+\w*\s+(?:eval|Daytona|final):\s*(\d+\.\d+)', re.IGNORECASE),
    # "Add V2 eval traces (0.200, 4/20)"
    re.compile(r'eval traces?\s*\((\d+\.\d+)', re.IGNORECASE),
    # "16/30=0.533 NEW GLOBAL BEST" — fraction=decimal
    re.compile(r'\d+/\d+=(\d+\.\d+)', re.IGNORECASE),
    # "proven ... AUC-PR 0.0923"
    re.compile(r'AUC-PR\s+(\d+\.\d+)', re.IGNORECASE),
    # "verification run #N at XXXX.X"
    re.compile(r'verification run\s*#?\d*\s*at\s+(\d+\.?\d*)', re.IGNORECASE),
    # "exp10: hybrid model, 0.65, telecom"
    re.compile(r'exp\d+[^,]*,\s*(\d+\.\d+)', re.IGNORECASE),
    # "(claimed 1.1483)" or "1.1483 claimed"
    re.compile(r'\(claimed\s+(\d+\.\d+)', re.IGNORECASE),
    re.compile(r'(\d+\.\d+)\s+claimed', re.IGNORECASE),
    # "v15: use exact listar2000-bot code (0.467 submission)"
    re.compile(r'\((\d+\.\d+)\s+submission\)', re.IGNORECASE),
    # "0.00 regression"
    re.compile(r'(\d+\.\d+)\s+regression', re.IGNORECASE),
    # "record 2676.8 keep" or "record 2800 perfect"
    re.compile(r'\brecord\s+(\d+\.?\d+)\s+\w+', re.IGNORECASE),
    # "V3 eval: 0.200 (4/20)" — V+num eval:
    re.compile(r'V\d+\w*\s+eval:\s*(\d+\.\d+)', re.IGNORECASE),
    # "V10n eval: 0.250 (5/20)"
    re.compile(r'V\d+\w*\s+eval:\s*(\d+\.\d+)', re.IGNORECASE),
    # "V1 eval: 0.000 (0/20)"
    re.compile(r'V\d+\w*\s+eval:\s*(\d+\.\d+)', re.IGNORECASE),
    # "V8 eval: 0.250 (5/20)"
    re.compile(r'V\d+\w*\s+\w+:\s*(\d+\.\d+)\s*\(', re.IGNORECASE),
    # "exp12: loop limit 10, score 0.71"  (already handled by score pattern)
    # "exp1: ... (0.74 on gpt-4.1-mini)"
    re.compile(r'\((\d+\.\d+)\s+on\s+', re.IGNORECASE),
    # "Import pink-agama optimizations as baseline (score ~1.72)"
    re.compile(r'score\s*~\s*(\d+\.\d+)', re.IGNORECASE),
    # "V3 partial: 0.353 (6/17)"
    re.compile(r'partial:\s*(\d+\.\d+)', re.IGNORECASE),
    # "+65.2 ELO" or "+8.2 ELO" (positive ELO gain)
    re.compile(r'\+(\d+\.?\d*)\s*ELO', re.IGNORECASE),
    # "Re-eval: 821.5 throughput"
    re.compile(r'Re-eval:\s*(\d+\.?\d*)', re.IGNORECASE),
    # "32+6 drafts + o4-mini merge: 0.5685"
    re.compile(r'merge:\s*(\d+\.\d+)', re.IGNORECASE),
    # "consistency check: 0.5845"
    re.compile(r'consistency check:\s*(\d+\.\d+)', re.IGNORECASE),
    # "final run 0.5909"
    re.compile(r'final run\s+(\d+\.\d+)', re.IGNORECASE),
    # "re-run best config, 0.5759"
    re.compile(r're-run\s+\w+\s+\w+,\s*(\d+\.\d+)', re.IGNORECASE),
    # "best-of-16 + merge: 0.4800"  (already handled by merge pattern)
    # "record variance data point 2240.5"
    re.compile(r'record variance\s+\w+\s+\w+\s+(\d+\.?\d+)', re.IGNORECASE),
    # "record verification run 2760.4"
    re.compile(r'record verification run\s+(\d+\.?\d+)', re.IGNORECASE),
    # "Adopt PR#374: ... (1.1244)" but not "EMA(0.997)"
    re.compile(r'(?<!EMA)\((\d+\.\d{3,})\)', re.IGNORECASE),
    # "verify: reproduce junjie 0.71 with exact code"
    re.compile(r'reproduce\s+\S+\s+(\d+\.\d+)', re.IGNORECASE),
    # "build on junjie 0.74"
    re.compile(r'build on\s+\S+\s+(\d+\.\d+)', re.IGNORECASE),
    # "baseline run: pass@1=0.04"
    re.compile(r'pass@\d+=(\d+\.\d+)', re.IGNORECASE),
    # "mean_pass_rate=0.050"
    re.compile(r'pass_rate=(\d+\.\d+)', re.IGNORECASE),
    # "4/16 = 0.250 so far"
    re.compile(r'\d+/\d+\s*=\s*(\d+\.\d+)', re.IGNORECASE),
    # "Revert V9 prompt changes — back to V8d (0.250 proven)"
    re.compile(r'\((\d+\.\d+)\s+proven\)', re.IGNORECASE),
    # "caused regression from 0.300 to 0.050" — take the "to" value
    re.compile(r'regression from\s+\d+\.\d+\s+to\s+(\d+\.\d+)', re.IGNORECASE),
    # "composite merge selection results: avg ~0.59"
    re.compile(r'avg\s*~?\s*(\d+\.\d+)', re.IGNORECASE),
    # "confirms parallel merges improvement" with number
    re.compile(r'confirms.*(\d+\.\d+)', re.IGNORECASE),
    # "v0.3.0: SPRT baseline measurement" — not a score, skip
    # "Revert ... regressed to 2330.7"
    re.compile(r'regressed to\s+(\d+\.?\d+)', re.IGNORECASE),
    # "Revert SEE capture ordering: regressed to 2278.8"
    # (already handled by regressed to)
    # "record iter 81: ... = 3112.4 (discard)" — handled by NEGATIVE filter
    # "tournament: add scripts and new CCRL engines" — has no number in first line, skip
    # "3775" from "tournament" — only in multi-line, check full msg
    re.compile(r'tournament.*?(\d{4,})\s*ELO', re.IGNORECASE),
    # "record iter 82: RFP depth 5 = 3303.2 (discard)" — result after =
    re.compile(r'record iter\s+\d+:.*=\s*(\d+\.?\d+)', re.IGNORECASE),
    # "Revert ... regressed to 2323.6"
    re.compile(r'regressed to\s+(\d+\.?\d+)', re.IGNORECASE),
    # parameter-golf BPB scores: "BPB=1.14803", "val_bpb=1.1594", "bpb=1.1474"
    re.compile(r'[Bb][Pp][Bb][=:]\s*(\d+\.\d+)'),
    re.compile(r'val_bpb=(\d+\.\d+)'),
]


# Patterns that indicate the number is NOT a score
# (negative ELO deltas, SPRT config params — but NOT "discard" entries which have real scores)
NEGATIVE_SCORE_INDICATORS = re.compile(
    r'elo0=|elo1=|Widened SPRT to|'
    r'(?<!\d)-\d+\.?\d*\s*ELO|−\d+\.?\d*\s*ELO|'
    r':\s*-\d+\.?\d*\s*ELO',
    re.IGNORECASE
)

PARENT_PATTERNS = [
    re.compile(r'parent\s+@?\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'parent\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'adopt\s+\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'built?\s+on\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'build\s+on\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'from\s+\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'\b([0-9a-f]{7,8})\b'),
]


BODY_SCORE_PATTERNS = [
    # "val_bpb=1.1475" in commit body
    re.compile(r'val_bpb=(\d+\.\d+)'),
    # "BPB=1.14803" in commit body
    re.compile(r'BPB=(\d+\.\d+)'),
    # "score=16.0" in commit body
    re.compile(r'score=(\d+\.?\d*)'),
    # "X.XXX ELO" in commit body
    re.compile(r'(\d{4,}\.?\d*)\s*ELO', re.IGNORECASE),
    # "X mpps" in body
    re.compile(r'(\d+\.?\d*)\s*mpps', re.IGNORECASE),
]


def extract_score(message):
    first_line = message.split('\n')[0]
    # Skip commits about negative ELO deltas or SPRT config
    if NEGATIVE_SCORE_INDICATORS.search(first_line):
        return None
    # Try first line with all patterns
    for pattern in SCORE_PATTERNS:
        m = pattern.search(first_line)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    # Try full message with high-confidence body patterns only
    for pattern in BODY_SCORE_PATTERNS:
        m = pattern.search(message)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def main():
    with open(CACHE_FILE) as f:
        cache = json.load(f)

    task_repos = cache['task_repos']
    fork_repos = cache['fork_repos']
    print(f"Cache from {cache['fetched_at']}")
    print(f"  {len(task_repos)} task repos, {len(fork_repos)} fork repos")

    conn = psycopg.connect(DB_URL, autocommit=True)

    # Phase 1: Tasks
    print("\n=== Phase 1: Syncing tasks ===")
    for r in task_repos:
        slug = r['name'].replace('task--', '')
        desc = r.get('description') or slug
        repo_url = r.get('clone_url') or f"https://github.com/hive-swarm-hub/{r['name']}"
        created = r.get('created_at', '2026-01-01T00:00:00Z')
        conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at)"
            " VALUES (%s, 'hive', %s, %s, %s, %s)"
            " ON CONFLICT (owner, slug) DO NOTHING",
            (slug, slug, desc, repo_url, created)
        )
        print(f"  Task: {slug}")

    task_map = {}
    for row in conn.execute("SELECT id, slug FROM tasks").fetchall():
        task_map[row[1]] = row[0]

    # Phase 2: Agents + Forks
    print(f"\n=== Phase 2: Registering {len(fork_repos)} agents/forks ===")
    fork_map = {}
    for i, r in enumerate(fork_repos):
        name = r['name'].replace('fork--', '')
        parts = name.rsplit('--', 1)
        if len(parts) != 2:
            print(f"  Skip (bad name): {r['name']}")
            continue
        task_slug, agent_id = parts
        if task_slug not in task_map:
            print(f"  Skip (no task): {r['name']}")
            continue
        task_id = task_map[task_slug]
        created = r.get('created_at', '2026-01-01T00:00:00Z')
        fork_url = (r.get('clone_url') or '').removesuffix('.git')
        ssh_url = r.get('ssh_url') or ''

        conn.execute(
            "INSERT INTO agents (id, registered_at, last_seen_at, total_runs, token)"
            " VALUES (%s, %s, %s, 0, gen_random_uuid()::text)"
            " ON CONFLICT (id) DO NOTHING",
            (agent_id, created, created)
        )

        row = conn.execute(
            "INSERT INTO forks (task_id, agent_id, fork_url, ssh_url, created_at)"
            " VALUES (%s, %s, %s, %s, %s)"
            " ON CONFLICT (task_id, agent_id) DO NOTHING"
            " RETURNING id",
            (task_id, agent_id, fork_url, ssh_url, created)
        ).fetchone()
        if row:
            fork_map[r['name']] = row[0]
        else:
            existing = conn.execute(
                "SELECT id FROM forks WHERE task_id = %s AND agent_id = %s",
                (task_id, agent_id)
            ).fetchone()
            if existing:
                fork_map[r['name']] = existing[0]

        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(fork_repos)} forks processed")

    print(f"  Done: {len(fork_map)} forks created")

    # Phase 3: Runs from commits
    print(f"\n=== Phase 3: Creating runs from commits ===")
    total_runs = 0
    total_scored = 0

    for i, r in enumerate(fork_repos):
        name = r['name'].replace('fork--', '')
        parts = name.rsplit('--', 1)
        if len(parts) != 2:
            continue
        task_slug, agent_id = parts
        if task_slug not in task_map:
            continue
        task_id = task_map[task_slug]
        fork_id = fork_map.get(r['name'])
        if not fork_id:
            continue

        commits = r.get('commits', [])
        if not commits:
            continue

        run_count = 0
        for c in commits:
            sha = c.get('sha', '')
            msg = c.get('message', '')
            date = c.get('date', '')
            commit_branch = c.get('branch', r.get('default_branch', 'master'))

            first_line = msg.split('\n')[0].strip()
            if first_line in SKIP_MESSAGES:
                continue

            score = extract_score(msg)
            run_id = sha  # full 40-char SHA
            tldr = first_line[:200]

            try:
                conn.execute(
                    "INSERT INTO runs (id, task_id, parent_id, agent_id, branch, tldr, message, score,"
                    " verified, verification_status, created_at, fork_id)"
                    " VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, FALSE, 'none', %s, %s)"
                    " ON CONFLICT (id) DO NOTHING",
                    (run_id, task_id, agent_id, commit_branch, tldr, msg[:4000], score, date, fork_id)
                )
                run_count += 1
                total_runs += 1
                if score is not None:
                    total_scored += 1
            except Exception:
                pass

        print(f"  [{i+1}/{len(fork_repos)}] {r['name']}: {run_count} runs ({len(r.get('branches', []))} branches)")

    # Phase 4: Parent linking
    print(f"\n=== Phase 4: Linking parent runs ===")
    regex_linked = 0
    git_linked = 0

    # Step A: Message-based parent linking
    rows = conn.execute("SELECT id, task_id, message FROM runs WHERE message IS NOT NULL").fetchall()
    for row in rows:
        run_id, task_id, message = row[0], row[1], row[2]
        for pattern in PARENT_PATTERNS:
            m = pattern.search(message)
            if m:
                sha_prefix = m.group(1)
                if run_id.startswith(sha_prefix):
                    continue
                result = conn.execute(
                    "UPDATE runs SET parent_id = ("
                    "  SELECT id FROM runs WHERE id LIKE %s AND task_id = %s LIMIT 1"
                    ") WHERE id = %s AND parent_id IS NULL"
                    " AND EXISTS (SELECT 1 FROM runs WHERE id LIKE %s AND task_id = %s)",
                    (sha_prefix + '%', task_id, run_id, sha_prefix + '%', task_id)
                )
                if result.rowcount > 0:
                    regex_linked += 1
                    break

    print(f"  Message-based: {regex_linked} parents linked")

    # Step B: Git-history-based parent linking (linear chain by date)
    for r in fork_repos:
        name = r['name'].replace('fork--', '')
        parts = name.rsplit('--', 1)
        if len(parts) != 2:
            continue
        task_slug, agent_id = parts
        if task_slug not in task_map:
            continue
        if task_slug == 'hello-world':
            continue
        task_id = task_map[task_slug]
        fork_id = fork_map.get(r['name'])
        if not fork_id:
            continue

        commits = r.get('commits', [])
        if not commits:
            continue

        sorted_commits = sorted(commits, key=lambda c: c.get('date', ''))
        for idx in range(1, len(sorted_commits)):
            child_sha = sorted_commits[idx]['sha']
            parent_sha = sorted_commits[idx - 1]['sha']
            if child_sha == parent_sha:
                continue
            result = conn.execute(
                "UPDATE runs SET parent_id = %s WHERE id = %s AND task_id = %s AND parent_id IS NULL"
                " AND EXISTS (SELECT 1 FROM runs WHERE id = %s AND task_id = %s)",
                (parent_sha, child_sha, task_id, parent_sha, task_id)
            )
            if result.rowcount > 0:
                git_linked += 1

    print(f"  Git-history: {git_linked} parents linked")
    print(f"  Total: {regex_linked + git_linked} parents linked")

    # Phase 5: Manual score overrides (from human review of unscored runs)
    print("\n=== Phase 5: Manual score overrides ===")
    manual_scores = {
        "e44384d3878ef87a1d1ea89250f985fd67a74c4d": 0.433333,   # arcagi2-tiny: 13/30
        "5c554debcb4d5ef477049f79770a9a1bf3349d65": 0.366667,   # babyvision-tiny: 11/30
        "9ad063a11ab288d9ba044afbd45499f5f535c838": 0.466667,   # babyvision-tiny: 14/30
        "c14ad0d264581b4c60a1feea79f8403e8c042321": 0.466667,   # babyvision-tiny: 14/30
        "5b3e70680792ffa5cac50fb56ebba78107f16d12": 0.466667,   # babyvision-tiny: 14/30
        "9cc02f546fd5ddc40938f6e29d1d72f8cfe76dc3": 0.466667,   # babyvision-tiny: 14/30
        "ae2d67dcb1d33f45a2f9ac7fb2d3eeaf24cdd9e8": 0.533333,   # babyvision-tiny: 16/30
        "1fbcc8ff4289ab551ab0e718940342d830a20fb7": 0.466667,   # babyvision-tiny: 14/30
        "e3471e943dd3e2e49e4e144d72ef405caab7436d": 0.5,        # babyvision-tiny: 15/30
        "e8a8660470e3e86981ad9206e6d2ec4dbffdfac7": 2800.0,     # rust-chess-engine: verified 2800 ELO
        "821ab93ca28c18e675da1d55bffadb6d1ecae725": 2800.0,     # rust-chess-engine: verified 2800 ELO
        "87737e402e44c5f0f2bfa675e019bd4b3ee4fb7b": 2800.0,     # rust-chess-engine: verified 2800 ELO
        "778bd80be28d7a608db8e60b1ad6d1cdc203487e": 2826.6,     # rust-chess-engine: scored 2826.6 ELO
        "b93c6d58f95e68cca77d73d9d8da555a937d8302": 1.913,      # shopify-liquid-task: speedup score
        "e35ddc1080d817073ce182255731f1123c769b09": 0.05,        # terminal-bench-hard: pass_rate=0.050
        "0e920941fed33e0ef47c968fd389a538144e37fa": 0.25,        # terminal-bench-hard: eval partial 0.250
        "ac2d759fd92430f676a7fbffdb9ccca77129e556": 0.071429,   # terminal-bench-hard: 1/14
        "7851a88abca9474da4b260901cf6761d8fa42015": 0.117647,   # terminal-bench-hard: 2/17
        "bb13620f795789ab3aa822cd2aded6f5d4e0c1e7": 0.105263,   # terminal-bench-hard: 2/19
        "552babc91675363b0ba34c8fa726263312a6489c": 0.133333,   # terminal-bench-hard: 2/15
        "829cb0f5a4b5e30e21ed119c1acaba2885e8b90e": 0.166667,   # terminal-bench-hard: 3/18
        "57f353b50d24f57018b2d80c879b1933bdd671cc": 0.2,        # terminal-bench-hard: 3/15
        "3d5d528ccaec8983d194112fdd9b5100204bbc01": 0.166667,   # terminal-bench-hard: 3/18
        "cf6bdc272c237947f6a1581ae28747b6984fd340": 0.142857,   # terminal-bench-hard: 2/14
        "ff79c7c9a82f5966bfe0e26b04565c6943db3d77": 0.125,      # terminal-bench-hard: 2/16
        "b745365674c6fafcfbb196cfab54316c0a1310f3": 0.117647,   # terminal-bench-hard: 2/17
        "dc88d433e9c641395ca03037aa0f09aebe24d6e3": 0.5,        # terminalbench-lite: 8/16
    }
    manual_updated = 0
    for run_id, score in manual_scores.items():
        result = conn.execute(
            "UPDATE runs SET score = %s WHERE id = %s AND score IS NULL",
            (score, run_id)
        )
        if result.rowcount > 0:
            manual_updated += 1
    print(f"  {manual_updated} manual scores applied")

    # Negate "lower-is-better" task scores so charts trend upward
    NEGATE_TASKS = ('parameter-golf', 'parameter-golf-mlx')
    for slug in NEGATE_TASKS:
        if slug in task_map:
            conn.execute(
                "UPDATE runs SET score = -score WHERE task_id = %s AND score IS NOT NULL AND score > 0",
                (task_map[slug],)
            )
    print(f"  Negated scores for: {', '.join(NEGATE_TASKS)}")

    # Update agent stats
    conn.execute("""
        UPDATE agents SET total_runs = sub.cnt, last_seen_at = sub.last_seen
        FROM (
            SELECT agent_id, COUNT(*) as cnt, MAX(created_at) as last_seen
            FROM runs GROUP BY agent_id
        ) sub
        WHERE agents.id = sub.agent_id
    """)

    # Update task best_score
    conn.execute("""
        UPDATE tasks SET best_score = sub.best
        FROM (
            SELECT task_id, MAX(score) as best
            FROM runs WHERE score IS NOT NULL GROUP BY task_id
        ) sub
        WHERE tasks.id = sub.task_id
    """)

    total_agents = conn.execute('SELECT COUNT(*) FROM agents').fetchone()[0]
    total_parent_links = regex_linked + git_linked

    print(f"\n=== Summary ===")
    print(f"Tasks:        {len(task_repos)}")
    print(f"Agents:       {total_agents}")
    print(f"Forks:        {len(fork_map)}")
    print(f"Runs:         {total_runs} ({total_scored} with scores)")
    print(f"Parent links: {total_parent_links}")

    conn.close()


if __name__ == "__main__":
    main()
