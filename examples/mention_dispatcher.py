"""Central mention dispatcher — one process watches all agents.

Polls the Hive API for all registered agents. When any agent has
unread mentions, spins up a sandbox via the Agent SDK, tells it
to check its inbox, marks mentions as read, and moves on.

Agent instances are cached in memory — the SDK keeps the session_id
after the first run(), so subsequent dispatches reuse the same sandbox.

No per-agent loops. No pre-registration. Just @ an agent in chat
and this process handles the rest.

Usage:
  HIVE_SERVER=http://localhost:8000 AGENT_API_URL=http://localhost:7778 \
    python examples/mention_dispatcher.py

Environment variables:
  HIVE_SERVER     — Hive server URL (default: http://localhost:8000)
  AGENT_API_URL   — Agent SDK server (default: http://localhost:7778)
  POLL_INTERVAL   — Seconds between polls (default: 15)
"""

import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "auto_feature_engineer", "src"))
from agent_sdk import Agent

SERVER = os.environ.get("HIVE_SERVER", "http://localhost:8000").rstrip("/")
API_URL = os.environ.get("AGENT_API_URL", "http://localhost:7778")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))

_agents: dict[str, Agent] = {}


def get_or_create_agent(agent_id: str, token: str) -> Agent:
    if agent_id not in _agents:
        print(f"[dispatch] Creating sandbox for {agent_id}")
        _agents[agent_id] = Agent(
            agent_id,
            provider=os.environ.get("AGENT_PROVIDER", "local"),
            tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
            skills={
                "hive": {"sources": [{"source": "rllm-org/hive", "type": "github"}]},
            },
            prompt=(
                f"You are {agent_id} on Hive.\n"
                f"The hive server is at {SERVER}.\n\n"
                f"IMPORTANT: Before doing anything else on first run, set up the hive CLI:\n"
                f"  pip install hive-evolve\n"
                f"  mkdir -p ~/.hive/agents\n"
                f'  echo \'{{"agent_id": "{agent_id}", "token": "{token}"}}\' > ~/.hive/agents/{agent_id}.json\n'
                f'  echo \'{{"server_url": "{SERVER}", "default_agent": "{agent_id}"}}\' > ~/.hive/config.json\n'
                f"  hive auth whoami  # verify it works\n"
            ),
            api_url=API_URL,
        )
    return _agents[agent_id]


def fetch_all_agents() -> list[dict]:
    import psycopg
    db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")
    with psycopg.connect(db_url) as conn:
        rows = conn.execute("SELECT id, token FROM agents").fetchall()
    return [{"id": r[0], "token": r[1]} for r in rows]


def fetch_all_tasks() -> list[dict]:
    resp = httpx.get(f"{SERVER}/api/tasks", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("tasks", data) if isinstance(data, dict) else data


def check_inbox(task_ref: str, token: str) -> dict:
    resp = httpx.get(
        f"{SERVER}/api/tasks/{task_ref}/inbox",
        params={"token": token, "status": "unread"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def mark_read(task_ref: str, token: str, ts: str):
    httpx.post(
        f"{SERVER}/api/tasks/{task_ref}/inbox/read",
        json={"ts": ts},
        params={"token": token},
        timeout=15,
    )


def main():
    print(f"Mention dispatcher started")
    print(f"  Hive server:  {SERVER}")
    print(f"  Agent SDK:    {API_URL}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print()

    while True:
        try:
            agents = fetch_all_agents()
            tasks = fetch_all_tasks()
            task_refs = [f"{t['owner']}/{t['slug']}" for t in tasks]

            for agent in agents:
                agent_id = agent["id"]
                token = agent.get("token") or agent_id

                for task_ref in task_refs:
                    try:
                        data = check_inbox(task_ref, token)
                        n = data.get("unread_count", 0)
                        if n == 0:
                            continue

                        latest_ts = data["mentions"][0]["ts"]
                        print(f"[{agent_id}] {n} unread mention(s) in {task_ref} — dispatching")

                        sdk_agent = get_or_create_agent(agent_id, token)
                        sdk_agent.run(
                            f"You have {n} unread mention(s) in your Hive inbox for task {task_ref}. "
                            f"Run `HIVE_SERVER={SERVER} hive inbox list --task {task_ref}` to see them, "
                            f"then handle each one appropriately."
                        )

                        mark_read(task_ref, token, latest_ts)
                        print(f"[{agent_id}] Done — marked as read up to ts={latest_ts}")

                    except Exception as e:
                        print(f"[{agent_id}] Error on {task_ref}: {e}")
                        if agent_id in _agents:
                            del _agents[agent_id]

        except Exception as e:
            print(f"[error] Poll cycle failed: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
