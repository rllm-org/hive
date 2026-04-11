#!/usr/bin/env python3
"""Reconstruct Hive DB from GitHub repos in hive-swarm-hub org."""

import json
import os
import re
import subprocess
import sys
import time

import psycopg

DB_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")
ORG = "hive-swarm-hub"
SKIP_MESSAGES = {"initial task upload", "Initial commit", "Add README"}

SCORE_PATTERNS = [
    re.compile(r'score[:\s=~]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*ELO', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*AUC', re.IGNORECASE),
    re.compile(r'accuracy[:\s]+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*(?:score|accuracy)', re.IGNORECASE),
    re.compile(r'improved to\s+(\d+\.?\d*)', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*mpps', re.IGNORECASE),
    re.compile(r'(\d+\.?\d*)\s*pass', re.IGNORECASE),
]

PARENT_PATTERNS = [
    re.compile(r'parent\s+@?\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'parent\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'adopt\s+\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'built?\s+on\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'build\s+on\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'from\s+\w+\s+([0-9a-f]{7,40})', re.IGNORECASE),
    re.compile(r'\b([0-9a-f]{7,8})\b'),
]

def gh_api(endpoint, paginate=False):
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  gh api error: {result.stderr[:200]}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # paginated output may be multiple JSON arrays concatenated
        # try to parse as JSONL
        items = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, list):
                        items.extend(parsed)
                    else:
                        items.append(parsed)
                except:
                    pass
        return items

def extract_score(message):
    for pattern in SCORE_PATTERNS:
        m = pattern.search(message)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None

def main():
    conn = psycopg.connect(DB_URL, autocommit=True)

    # Get all repos
    print("Fetching repos from hive-swarm-hub...")
    repos = gh_api(f"orgs/{ORG}/repos?per_page=100&type=public", paginate=True)
    print(f"Found {len(repos)} repos")

    task_repos = [r for r in repos if r['name'].startswith('task--')]
    fork_repos = [r for r in repos if r['name'].startswith('fork--')]

    print(f"  Tasks: {len(task_repos)}")
    print(f"  Forks: {len(fork_repos)}")

    # Phase 1: Tasks
    print("\n=== Phase 1: Syncing tasks ===")
    for r in task_repos:
        slug = r['name'].replace('task--', '')
        desc = r.get('description') or slug
        repo_url = r.get('clone_url') or f"https://github.com/{ORG}/{r['name']}"
        created = r.get('created_at', '2026-01-01T00:00:00Z')
        conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at)"
            " VALUES (%s, 'hive', %s, %s, %s, %s)"
            " ON CONFLICT (owner, slug) DO NOTHING",
            (slug, slug, desc, repo_url, created)
        )
        print(f"  Task: {slug}")

    # Build task lookup
    task_map = {}
    for row in conn.execute("SELECT id, slug FROM tasks").fetchall():
        task_map[row[1]] = row[0]

    # Phase 2: Agents + Forks
    print(f"\n=== Phase 2: Registering {len(fork_repos)} agents/forks ===")
    fork_map = {}  # repo_name -> fork_id
    for i, r in enumerate(fork_repos):
        name = r['name'].replace('fork--', '')
        # agent is last segment after --
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
        fork_url = r.get('clone_url') or ''
        ssh_url = r.get('ssh_url') or ''

        # Register agent
        conn.execute(
            "INSERT INTO agents (id, registered_at, last_seen_at, total_runs, token)"
            " VALUES (%s, %s, %s, 0, gen_random_uuid()::text)"
            " ON CONFLICT (id) DO NOTHING",
            (agent_id, created, created)
        )

        # Create fork
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
            # Already exists, look up
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

        # Get default branch
        repo_info = gh_api(f"repos/{ORG}/{r['name']}")
        if isinstance(repo_info, list):
            repo_info = repo_info[0] if repo_info else {}
        branch = repo_info.get('default_branch', 'master')
        time.sleep(0.3)

        # Get all branches
        try:
            branches_result = subprocess.run(
                ["gh", "api", f"repos/{ORG}/{r['name']}/branches", "--jq", ".[].name"],
                capture_output=True, text=True, timeout=60
            )
            if branches_result.returncode == 0:
                all_branches = [b.strip() for b in branches_result.stdout.splitlines() if b.strip()]
            else:
                all_branches = [branch]
        except Exception:
            all_branches = [branch]
        time.sleep(0.3)

        # Collect commits from all branches, deduplicated by SHA
        # Value: (commit_obj, branch_name) — prefer non-default branch
        commits_by_sha = {}
        for branch_name in all_branches:
            branch_commits = gh_api(
                f"repos/{ORG}/{r['name']}/commits?per_page=100&sha={branch_name}",
                paginate=True
            )
            time.sleep(0.3)
            for c in (branch_commits or []):
                sha = c.get('sha', '')
                if not sha:
                    continue
                if sha not in commits_by_sha:
                    commits_by_sha[sha] = (c, branch_name)
                elif branch_name != branch:
                    # prefer non-default branch (more specific)
                    commits_by_sha[sha] = (c, branch_name)

        if not commits_by_sha:
            continue

        run_count = 0
        for sha, (c, commit_branch) in commits_by_sha.items():
            msg = c.get('commit', {}).get('message', '') if isinstance(c.get('commit'), dict) else ''
            date = c.get('commit', {}).get('author', {}).get('date', '') if isinstance(c.get('commit'), dict) else ''

            # Skip boilerplate commits
            first_line = msg.split('\n')[0].strip()
            if first_line in SKIP_MESSAGES:
                continue

            score = extract_score(msg)
            run_id = sha[:8]
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
            except Exception as e:
                # SHA collision or other error, try with longer SHA
                run_id = sha[:12]
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
                except Exception as e2:
                    pass

        print(f"  [{i+1}/{len(fork_repos)}] {r['name']}: {run_count} runs ({len(all_branches)} branches)")

    # Phase 3b: Link parent runs
    print(f"\n=== Phase 3b: Linking parent runs ===")
    regex_linked = 0
    git_linked = 0

    # Step A: Message-based parent linking
    rows = conn.execute("SELECT id, task_id, message FROM runs WHERE message IS NOT NULL").fetchall()
    for row in rows:
        run_id = row[0]
        task_id = row[1]
        message = row[2]
        for pattern in PARENT_PATTERNS:
            m = pattern.search(message)
            if m:
                sha_prefix = m.group(1)[:8]
                if sha_prefix == run_id[:8]:
                    continue  # skip self-reference
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

    print(f"  Phase 3b message-based: {regex_linked} parents linked")

    # Step B: Git-history-based parent linking
    for i, r in enumerate(fork_repos):
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

        run_ids = [row[0] for row in conn.execute(
            "SELECT id FROM runs WHERE fork_id = %s AND parent_id IS NULL",
            (fork_id,)
        ).fetchall()]

        for run_id in run_ids:
            parent_data = gh_api(f"repos/{ORG}/{r['name']}/commits/{run_id}")
            time.sleep(0.3)
            if isinstance(parent_data, dict):
                parents = parent_data.get('parents', [])
                if parents:
                    parent_sha = parents[0].get('sha', '')[:8]
                    if parent_sha:
                        result = conn.execute(
                            "UPDATE runs SET parent_id = ("
                            "  SELECT id FROM runs WHERE id LIKE %s AND task_id = %s LIMIT 1"
                            ") WHERE id = %s AND parent_id IS NULL"
                            " AND EXISTS (SELECT 1 FROM runs WHERE id LIKE %s AND task_id = %s)",
                            (parent_sha + '%', task_id, run_id, parent_sha + '%', task_id)
                        )
                        if result.rowcount > 0:
                            git_linked += 1

        if (i + 1) % 10 == 0:
            print(f"  git-history: {i+1}/{len(fork_repos)} forks processed, {git_linked} linked so far")

    print(f"  Phase 3b git-history: {git_linked} parents linked")
    print(f"  Total parents linked: {regex_linked + git_linked}")

    # Update agent total_runs
    conn.execute("""
        UPDATE agents SET total_runs = sub.cnt, last_seen_at = sub.last_seen
        FROM (
            SELECT agent_id, COUNT(*) as cnt, MAX(created_at) as last_seen
            FROM runs GROUP BY agent_id
        ) sub
        WHERE agents.id = sub.agent_id
    """)

    # Update task best_score and improvements
    conn.execute("""
        UPDATE tasks SET best_score = sub.best
        FROM (
            SELECT task_id, MAX(score) as best
            FROM runs WHERE score IS NOT NULL GROUP BY task_id
        ) sub
        WHERE tasks.id = sub.task_id
    """)

    print(f"\n=== Summary ===")
    print(f"Tasks: {len(task_repos)}")
    print(f"Agents: {conn.execute('SELECT COUNT(*) FROM agents').fetchone()[0]}")
    print(f"Forks: {len(fork_map)}")
    print(f"Runs: {total_runs} ({total_scored} with scores)")

    conn.close()

if __name__ == "__main__":
    main()
