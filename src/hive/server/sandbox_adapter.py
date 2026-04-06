"""Adapter that runs inside a Daytona sandbox, bridging Claude Code ↔ Hive.

Usage (inside sandbox):
    HIVE_SERVER_URL=https://... HIVE_ADAPTER_TOKEN=... HIVE_SANDBOX_ID=...
    python -m hive.server.sandbox_adapter

The adapter:
1. Waits for an active session with pending user messages
2. Runs Claude Code with each message via `claude -p "..." --output-format stream-json`
3. Streams output events back to Hive via the sandbox-hook API
4. Supports multi-turn conversations via --resume
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any

import httpx

log = logging.getLogger("hive.adapter")

SERVER_URL = os.environ.get("HIVE_SERVER_URL", "").rstrip("/")
ADAPTER_TOKEN = os.environ.get("HIVE_ADAPTER_TOKEN", "")
SANDBOX_ID = os.environ.get("HIVE_SANDBOX_ID", "")
PROVIDER = os.environ.get("HIVE_PROVIDER", "claude_code")
APPROVAL_MODE = os.environ.get("HIVE_APPROVAL_MODE", "guarded")
WORK_DIR = os.environ.get("HIVE_CWD", "/home/daytona")
POLL_INTERVAL = int(os.environ.get("HIVE_ADAPTER_POLL_INTERVAL", "2"))
HOOK_BASE = f"{SERVER_URL}/api/sandbox-hook"


def _headers() -> dict[str, str]:
    return {"X-Sandbox-Token": ADAPTER_TOKEN, "Content-Type": "application/json"}


def _post(path: str, body: dict) -> dict:
    resp = httpx.post(f"{HOOK_BASE}{path}", json=body, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get(path: str, params: dict | None = None) -> dict:
    resp = httpx.get(f"{HOOK_BASE}{path}", params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json()


def push_events(session_id: str, events: list[dict]) -> None:
    if not events:
        return
    _post("/events", {"session_id": session_id, "events": events})


def poll_pending(session_id: str, after_seq: int) -> tuple[list[dict], str]:
    data = _get("/pending", {"session_id": session_id, "after_seq": after_seq})
    return data.get("messages", []), data.get("session_status", "running")


def update_session(session_id: str, status: str) -> None:
    _post("/session-update", {"session_id": session_id, "status": status})


def heartbeat() -> None:
    _post("/heartbeat", {})


def _build_claude_cmd(
    prompt: str,
    conversation_id: str | None,
    approval_mode: str,
) -> list[str]:
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json"]
    if conversation_id:
        cmd.extend(["--resume", conversation_id])
    if approval_mode == "auto_accept":
        cmd.append("--dangerously-skip-permissions")
    return cmd


def _map_claude_event(raw: dict) -> dict[str, Any] | None:
    """Map a Claude Code stream-json event to a Hive session event."""
    etype = raw.get("type", "")

    if etype == "assistant":
        content = raw.get("message", {}).get("content", [])
        text_parts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
        if text_parts:
            return {"type": "message.assistant", "data": {"text": "\n".join(text_parts)}}

    if etype == "tool_use":
        return {"type": "tool.call.started", "data": {
            "tool": raw.get("name", raw.get("tool", "")),
            "input": raw.get("input", {}),
        }}

    if etype == "tool_result":
        return {"type": "tool.call.finished", "data": {
            "content": raw.get("content", ""),
        }}

    if etype == "result":
        return {"type": "session.completed", "data": {
            "result": raw.get("result", ""),
            "cost": raw.get("cost", {}),
            "conversation_id": raw.get("conversation_id"),
        }}

    if etype == "error":
        return {"type": "session.failed", "data": {
            "error": raw.get("error", str(raw)),
        }}

    # Forward unknown events as stdout chunks
    if etype and etype not in ("system",):
        return {"type": "stdout.chunk", "data": {"raw": raw}}

    return None


def run_claude(session_id: str, prompt: str, conversation_id: str | None) -> str | None:
    """Run Claude Code, stream events to Hive, return conversation_id for continuation."""
    cmd = _build_claude_cmd(prompt, conversation_id, APPROVAL_MODE)
    log.info("running: %s", " ".join(cmd[:4]) + " ...")

    push_events(session_id, [{"type": "tool.call.started", "data": {
        "tool": "claude_code", "input": {"prompt": prompt[:500]},
    }}])

    new_conversation_id = conversation_id
    batch: list[dict] = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=WORK_DIR,
            text=True,
        )

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                batch.append({"type": "stdout.chunk", "data": {"text": line}})
                continue

            event = _map_claude_event(raw)
            if event:
                batch.append(event)

            # Extract conversation_id for multi-turn
            if raw.get("type") == "result" and raw.get("conversation_id"):
                new_conversation_id = raw["conversation_id"]

            # Flush batch periodically
            if len(batch) >= 10:
                push_events(session_id, batch)
                batch = []

        proc.wait()

        # Capture stderr
        stderr = proc.stderr.read() if proc.stderr else ""
        if stderr.strip():
            batch.append({"type": "stderr.chunk", "data": {"text": stderr.strip()}})

        if proc.returncode != 0:
            batch.append({"type": "session.failed", "data": {
                "exit_code": proc.returncode,
                "error": stderr.strip()[:2000] if stderr else f"exit code {proc.returncode}",
            }})

    except Exception as exc:
        batch.append({"type": "session.failed", "data": {"error": str(exc)}})
        log.exception("claude process error")

    # Flush remaining events
    push_events(session_id, batch)
    return new_conversation_id


def find_active_session(sandbox_id: str) -> str | None:
    """Find the most recent running session for this sandbox via pending poll."""
    # The adapter doesn't have direct DB access — it discovers sessions
    # by checking if there are pending messages. The session_id comes from
    # the messages themselves. For bootstrap, we read it from env.
    return os.environ.get("HIVE_SESSION_ID")


def main_loop() -> None:
    session_id = os.environ.get("HIVE_SESSION_ID", "")
    if not session_id:
        log.info("no HIVE_SESSION_ID set, waiting for session...")
        # In a future version, poll for active sessions
        while not session_id:
            time.sleep(POLL_INTERVAL)
            session_id = os.environ.get("HIVE_SESSION_ID", "")

    log.info("adapter started: sandbox=%s session=%s provider=%s", SANDBOX_ID, session_id, PROVIDER)

    last_seq = -1
    conversation_id: str | None = None

    while True:
        try:
            heartbeat()
            messages, session_status = poll_pending(session_id, last_seq)

            if session_status in ("completed", "failed", "interrupted"):
                log.info("session %s is %s, stopping", session_id, session_status)
                break

            for msg in messages:
                last_seq = msg["seq"]
                text = msg.get("data", {}).get("text", "")
                if not text:
                    continue
                log.info("processing message seq=%d: %s", last_seq, text[:80])
                conversation_id = run_claude(session_id, text, conversation_id)

        except httpx.HTTPStatusError as exc:
            log.warning("API error: %s %s", exc.response.status_code, exc.response.text[:200])
        except httpx.RequestError as exc:
            log.warning("connection error: %s", exc)
        except Exception:
            log.exception("adapter loop error")

        time.sleep(POLL_INTERVAL)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    if not SERVER_URL or not ADAPTER_TOKEN or not SANDBOX_ID:
        log.error("HIVE_SERVER_URL, HIVE_ADAPTER_TOKEN, and HIVE_SANDBOX_ID are required")
        sys.exit(1)
    main_loop()


if __name__ == "__main__":
    main()
