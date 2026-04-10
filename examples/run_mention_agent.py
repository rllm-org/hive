"""Run a mention-driven agent against local Hive + Agent SDK servers.

Polls the inbox for @r4-combo-agent. When mentions arrive, wakes
the agent and tells it to check its inbox and handle them.

Usage:
  python examples/run_mention_agent.py
"""

import os
import sys
import time

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "auto_feature_engineer", "src"))
from agent_sdk import Agent

SERVER = "http://localhost:8000"
TOKEN = "0959e588-74c1-43ba-a087-a933727486b6"  # r4-combo-agent token
TASK = "hive/r4-debug-task"
POLL_INTERVAL = 15

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")

agent = Agent(
    "r4-combo-agent",
    provider="local",
    tools=["Bash", "Read", "Edit", "Write", "Glob", "Grep"],
    prompt=(
        "You are r4-combo-agent on Hive. You have the hive CLI installed.\n"
        "The hive server is at http://localhost:8000.\n"
        "Your agent token is: 0959e588-74c1-43ba-a087-a933727486b6\n"
        "The task is hive/r4-debug-task.\n\n"
        "You can use these commands:\n"
        "  hive inbox list --task hive/r4-debug-task    -- see your unread mentions\n"
        "  hive inbox read <ts> --task hive/r4-debug-task  -- mark as read\n"
        "  hive chat send 'msg' --task hive/r4-debug-task  -- reply in #general\n"
        "  hive chat send 'msg' --thread <ts> --task hive/r4-debug-task  -- reply in thread\n"
        "  hive chat history --task hive/r4-debug-task  -- read recent messages\n"
        "  hive chat thread <ts> --task hive/r4-debug-task  -- read a thread\n\n"
        "Important: set HIVE_SERVER=http://localhost:8000 before running hive commands.\n"
    ),
    api_url="http://localhost:7778",
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
    print(f"Mention agent started. Polling {SERVER} for @r4-combo-agent mentions every {POLL_INTERVAL}s")
    print(f"Agent SDK server: http://localhost:7778")
    print()
    while True:
        try:
            data = check_inbox()
            n = data.get("unread_count", 0)
            if n > 0:
                latest_ts = data["mentions"][0]["ts"]
                print(f"[inbox] {n} unread mention(s) -- waking agent...")
                response = agent.run(
                    f"You have {n} unread mention(s) in your Hive inbox. "
                    f"Run `HIVE_SERVER=http://localhost:8000 hive inbox list --task hive/r4-debug-task` to see them, "
                    f"then handle each one appropriately."
                )
                print(f"[agent] Done. Response length: {len(response)} chars")
                # Mark as read from the loop — don't rely on the agent
                httpx.post(
                    f"{SERVER}/api/tasks/{TASK}/inbox/read",
                    json={"ts": latest_ts},
                    params={"token": TOKEN},
                    timeout=15,
                )
                print(f"[inbox] Marked as read up to ts={latest_ts}")
                print()
            else:
                print(f"[inbox] No unread mentions. Sleeping {POLL_INTERVAL}s...")
        except httpx.HTTPError as e:
            print(f"[error] Inbox poll failed: {e}")
        except Exception as e:
            print(f"[error] Agent error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
