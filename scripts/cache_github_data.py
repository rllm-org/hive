#!/usr/bin/env python3
"""Fetch all data from hive-swarm-hub GitHub org and save to a local JSON cache."""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone

ORG = "hive-swarm-hub"
CACHE_FILE = "scripts/github_cache.json"


def gh_api(endpoint, paginate=False):
    cmd = ["gh", "api", endpoint]
    if paginate:
        cmd.append("--paginate")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  gh api error: {result.stderr[:200]}", file=sys.stderr)
        return []
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
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


def fetch_branches(repo_name):
    result = subprocess.run(
        ["gh", "api", f"repos/{ORG}/{repo_name}/branches", "--jq", ".[].name"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode == 0:
        return [b.strip() for b in result.stdout.splitlines() if b.strip()]
    return []


def fetch_commits_for_repo(repo_name, default_branch, branches):
    commits_by_sha = {}
    for branch_name in branches:
        branch_commits = gh_api(
            f"repos/{ORG}/{repo_name}/commits?per_page=100&sha={branch_name}",
            paginate=True
        )
        time.sleep(0.3)
        for c in (branch_commits or []):
            sha = c.get('sha', '')
            if not sha:
                continue
            if sha not in commits_by_sha:
                commits_by_sha[sha] = (c, branch_name)
            elif branch_name != default_branch:
                commits_by_sha[sha] = (c, branch_name)

    commits = []
    for sha, (c, branch_name) in commits_by_sha.items():
        commit_obj = c.get('commit', {})
        msg = commit_obj.get('message', '') if isinstance(commit_obj, dict) else ''
        date = ''
        if isinstance(commit_obj, dict):
            author = commit_obj.get('author', {})
            date = author.get('date', '') if isinstance(author, dict) else ''
        commits.append({
            'sha': sha,
            'message': msg,
            'date': date,
            'branch': branch_name,
        })
    return commits


def main():
    print("Fetching repos from hive-swarm-hub...")
    repos = gh_api(f"orgs/{ORG}/repos?per_page=100&type=public", paginate=True)
    print(f"Found {len(repos)} repos")

    task_repos = [r for r in repos if r['name'].startswith('task--')]
    fork_repos = [r for r in repos if r['name'].startswith('fork--')]
    print(f"  Tasks: {len(task_repos)}")
    print(f"  Forks: {len(fork_repos)}")

    cached_tasks = []
    for r in task_repos:
        cached_tasks.append({
            'name': r['name'],
            'created_at': r.get('created_at'),
            'clone_url': r.get('clone_url'),
            'description': r.get('description'),
        })

    cached_forks = []
    for i, r in enumerate(fork_repos):
        repo_name = r['name']
        default_branch = r.get('default_branch', 'master')

        branches = fetch_branches(repo_name)
        time.sleep(0.3)
        if not branches:
            branches = [default_branch]

        commits = fetch_commits_for_repo(repo_name, default_branch, branches)

        cached_forks.append({
            'name': repo_name,
            'created_at': r.get('created_at'),
            'default_branch': default_branch,
            'clone_url': r.get('clone_url'),
            'ssh_url': r.get('ssh_url'),
            'description': r.get('description'),
            'branches': branches,
            'commits': commits,
        })

        print(f"[{i+1}/{len(fork_repos)}] {repo_name}: {len(commits)} commits ({len(branches)} branches)")

    cache = {
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'task_repos': cached_tasks,
        'fork_repos': cached_forks,
    }

    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)

    print(f"\nCache written to {CACHE_FILE}")
    print(f"  {len(cached_tasks)} task repos")
    print(f"  {len(cached_forks)} fork repos")
    total_commits = sum(len(fr['commits']) for fr in cached_forks)
    print(f"  {total_commits} total commits")


if __name__ == "__main__":
    main()
