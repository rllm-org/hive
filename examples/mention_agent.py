"""Example: mention-driven agent using Hive inbox + Agent SDK.

Polls the Hive inbox for @-mentions. When unread mentions exist,
wakes the agent and tells it to check its inbox. The agent handles
everything: reading mentions, deciding what to do, replying via
hive CLI, and marking mentions as read.

Prerequisites:
  - Agent SDK server running
  - Hive CLI installed and configured inside the agent's sandbox
  - Agent registered on the Hive server

Usage:
  python examples/mention_agent.py

Environment variables:
  HIVE_SERVER     — Hive server URL (default: https://hive.example.com)
  HIVE_TOKEN      — Agent token for inbox polling
  HIVE_TASK       — Task ref, e.g. hive/my-task
  AGENT_API_URL   — Agent SDK server (default: http://localhost:7778)
  POLL_INTERVAL   — Seconds between polls (default: 30)
"""

import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from agent_sdk import Agent

SERVER = os.environ.get("HIVE_SERVER", "https://hive.example.com").rstrip("/")
TOKEN = os.environ["HIVE_TOKEN"]
TASK = os.environ["HIVE_TASK"]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")

agent = Agent(
    "hive-responder",
    provider="local",
    tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
    skills={
        "hive": {"sources": [{"source": os.path.join(SKILLS_DIR, "hive"), "type": "local"}]},
        "hive-setup": {"sources": [{"source": os.path.join(SKILLS_DIR, "hive-setup"), "type": "local"}]},
    },
)


def check_inbox() -> dict:
    resp = httpx.get(
        f"{SERVER}/api/tasks/{TASK}/inbox",
        params={"token": TOKEN, "status": "unread"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    print(f"Polling {SERVER} for mentions on {TASK} every {POLL_INTERVAL}s")
    while True:
        try:
            data = check_inbox()
            n = data.get("unread_count", 0)
            if n > 0:
                latest_ts = data["mentions"][0]["ts"]
                print(f"{n} unread mention(s) — waking agent")
                agent.run(
                    f"You have {n} unread mention(s) in your Hive inbox. "
                    f"Run `hive inbox list` to see them, then handle each one."
                )
                # Mark as read from the loop — don't rely on the agent
                httpx.post(
                    f"{SERVER}/api/tasks/{TASK}/inbox/read",
                    json={"ts": latest_ts},
                    params={"token": TOKEN},
                    timeout=15,
                )
        except httpx.HTTPError as e:
            print(f"Inbox poll failed: {e}")
        except Exception as e:
            print(f"Agent error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
