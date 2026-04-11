"""Central mention dispatcher — one process watches all agents.

Polls the Hive API for all registered agents. When any agent has
unread mentions, spins up a sandbox via the Agent SDK, tells it
to check its inbox, marks mentions as read, and moves on.

Uses async I/O — inbox checks run concurrently each cycle, agent
runs are spawned as background tasks so they don't block polling.

Usage:
  HIVE_SERVER=http://localhost:8000 AGENT_API_URL=http://localhost:7778 \
    python examples/mention_dispatcher.py

Environment variables:
  HIVE_SERVER     — Hive server URL (default: http://localhost:8000)
  AGENT_API_URL   — Agent SDK server (default: http://localhost:7778)
  AGENT_PROVIDER  — Sandbox provider: local or daytona (default: local)
  POLL_INTERVAL   — Seconds between polls (default: 15)
  DATABASE_URL    — Postgres URL for reading agent tokens
"""

import asyncio
import os

import httpx

from agent_sdk import Agent

SERVER = os.environ.get("HIVE_SERVER", "http://localhost:8000").rstrip("/")
AGENT_HIVE_SERVER = os.environ.get("AGENT_HIVE_SERVER", SERVER).rstrip("/")
API_URL = os.environ.get("AGENT_API_URL", "http://localhost:7778")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))
# Dockerfile for Daytona sandboxes — python:3.12-slim + hive-evolve + sandbox-agent.
_DOCKERFILE_PATH = os.path.join(os.path.dirname(__file__), "Dockerfile.hive-agent")


_agents: dict[str, Agent] = {}
_in_flight: set[str] = set()


def get_or_create_agent(agent_id: str, token: str) -> Agent:
    if agent_id not in _agents:
        print(f"[dispatch] Creating sandbox for {agent_id}")
        provider = os.environ.get("AGENT_PROVIDER", "local")
        _agents[agent_id] = Agent(
            agent_id,
            provider=provider,
            tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
            skills={
                "hive": {"sources": [{"source": "rllm-org/hive", "type": "github"}]},
            },
            dockerfile=_DOCKERFILE_PATH if provider == "daytona" else None,
            prompt=(
                f"You are {agent_id} on Hive. Python and hive CLI are pre-installed.\n"
                f"The hive server is at {AGENT_HIVE_SERVER}.\n\n"
                f"On first run, configure the hive CLI:\n"
                f"  mkdir -p ~/.hive/agents\n"
                f'  echo \'{{"agent_id": "{agent_id}", "token": "{token}"}}\' > ~/.hive/agents/{agent_id}.json\n'
                f'  echo \'{{"server_url": "{AGENT_HIVE_SERVER}", "default_agent": "{agent_id}"}}\' > ~/.hive/config.json\n'
                f"  hive auth whoami\n"
            ),
            api_url=API_URL,
        )
    return _agents[agent_id]


async def fetch_all_agents() -> list[dict]:
    """Fetch cloud agents only — local agents handle their inbox themselves."""
    import psycopg
    db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")
    loop = asyncio.get_running_loop()
    def _query():
        with psycopg.connect(db_url) as conn:
            return conn.execute(
                "SELECT id, token FROM agents WHERE type = 'cloud'"
            ).fetchall()
    rows = await loop.run_in_executor(None, _query)
    return [{"id": r[0], "token": r[1]} for r in rows]


async def fetch_all_tasks(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(f"{SERVER}/api/tasks", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data.get("tasks", data) if isinstance(data, dict) else data


async def check_inbox(client: httpx.AsyncClient, task_ref: str, token: str) -> dict | None:
    try:
        resp = await client.get(
            f"{SERVER}/api/tasks/{task_ref}/inbox",
            params={"token": token, "status": "unread"},
            timeout=30,
        )
        if resp.status_code == 401:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


async def mark_read(client: httpx.AsyncClient, task_ref: str, token: str, ts: str):
    await client.post(
        f"{SERVER}/api/tasks/{task_ref}/inbox/read",
        json={"ts": ts},
        params={"token": token},
        timeout=15,
    )


async def run_agent(client: httpx.AsyncClient, agent_id: str, token: str, task_ref: str, n: int, latest_ts: str):
    """Background task: run the agent and mark read when done."""
    try:
        sdk_agent = get_or_create_agent(agent_id, token)
        await sdk_agent.arun(
            f"You have {n} unread mention(s) in your Hive inbox for task {task_ref}. "
            f"Run `HIVE_SERVER={AGENT_HIVE_SERVER} hive inbox list --task {task_ref}` to see them, "
            f"then handle each one appropriately."
        )
        await mark_read(client, task_ref, token, latest_ts)
        print(f"[{agent_id}] Done — marked as read up to ts={latest_ts}")
    except Exception as e:
        print(f"[{agent_id}] Error on {task_ref}: {e}")
        if agent_id in _agents:
            del _agents[agent_id]
    finally:
        _in_flight.discard(agent_id)


async def poll_cycle(client: httpx.AsyncClient):
    """One poll cycle: check all inboxes concurrently, spawn agent runs as background tasks."""
    agents = await fetch_all_agents()
    tasks = await fetch_all_tasks(client)
    task_refs = [f"{t['owner']}/{t['slug']}" for t in tasks]

    # Phase 1: check all inboxes concurrently (fast — just HTTP GETs)
    inbox_checks = []
    for agent in agents:
        for task_ref in task_refs:
            inbox_checks.append((agent, task_ref, check_inbox(client, task_ref, agent.get("token") or agent["id"])))

    results = await asyncio.gather(*[c[2] for c in inbox_checks], return_exceptions=True)

    # Phase 2: for any agent with mentions, spawn arun as a background task
    for (agent, task_ref, _), data in zip(inbox_checks, results):
        if isinstance(data, Exception) or data is None:
            continue
        n = data.get("unread_count", 0)
        if n == 0:
            continue

        agent_id = agent["id"]
        token = agent.get("token") or agent_id

        if agent_id in _in_flight:
            continue

        latest_ts = data["mentions"][0]["ts"]
        print(f"[{agent_id}] {n} unread mention(s) in {task_ref} — dispatching")
        _in_flight.add(agent_id)
        asyncio.create_task(run_agent(client, agent_id, token, task_ref, n, latest_ts))


async def main():
    print(f"Mention dispatcher started")
    print(f"  Hive server:  {SERVER}")
    print(f"  Agent SDK:    {API_URL}")
    print(f"  Poll interval: {POLL_INTERVAL}s")
    print()

    async with httpx.AsyncClient() as client:
        while True:
            try:
                await poll_cycle(client)
            except Exception as e:
                print(f"[error] Poll cycle failed: {e}")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
