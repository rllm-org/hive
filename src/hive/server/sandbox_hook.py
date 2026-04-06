"""Ingestion endpoints called by the adapter running inside a Daytona sandbox.

Auth: X-Sandbox-Token header (generated at provision, stored on task_sandboxes).
These endpoints let the adapter push Claude Code output events and poll for
user messages to relay into the agent process.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from .db import get_db, now
from .sandbox_helpers import insert_session_event

router = APIRouter(prefix="/api/sandbox-hook")


async def _require_sandbox(x_sandbox_token: str = Header(...)) -> dict:
    """Validate the adapter token and return the sandbox row."""
    if not x_sandbox_token:
        raise HTTPException(401, "X-Sandbox-Token required")
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT id, task_id FROM task_sandboxes"
                " WHERE adapter_token = %s AND status IN ('ready', 'running')",
                (x_sandbox_token,),
            )
        ).fetchone()
    if not row:
        raise HTTPException(401, "invalid or expired sandbox token")
    return dict(row)


def _validate_session(session_row: dict | None, sandbox_id: str) -> dict:
    if not session_row:
        raise HTTPException(404, "session not found")
    if session_row["sandbox_id"] != sandbox_id:
        raise HTTPException(403, "session does not belong to this sandbox")
    return session_row


# --- Push events (adapter → Hive) ---


@router.post("/events")
async def push_events(body: dict[str, Any], x_sandbox_token: str = Header(...)):
    """Adapter pushes Claude Code output events into a session's event stream."""
    sb = await _require_sandbox(x_sandbox_token)
    session_id = body.get("session_id")
    events = body.get("events")
    if not session_id or not isinstance(session_id, str):
        raise HTTPException(400, "session_id required")
    if not events or not isinstance(events, list):
        raise HTTPException(400, "events list required")

    async with get_db() as conn:
        session = await (
            await conn.execute(
                "SELECT id, sandbox_id, status FROM agent_sessions WHERE id = %s",
                (session_id,),
            )
        ).fetchone()
        _validate_session(session, sb["id"])

        inserted = 0
        for ev in events:
            if not isinstance(ev, dict):
                continue
            etype = ev.get("type", "unknown")
            data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
            await insert_session_event(conn, session_id, etype, data)
            inserted += 1

        await conn.execute(
            "UPDATE task_sandboxes SET last_active_at = %s WHERE id = %s",
            (now(), sb["id"]),
        )
    return {"inserted": inserted}


# --- Poll for user messages (adapter ← Hive) ---


@router.get("/pending")
async def pending_messages(
    session_id: str = Query(...),
    after_seq: int = Query(-1, ge=-1),
    x_sandbox_token: str = Header(...),
):
    """Adapter polls for user messages it hasn't processed yet."""
    sb = await _require_sandbox(x_sandbox_token)
    async with get_db() as conn:
        session = await (
            await conn.execute(
                "SELECT id, sandbox_id, status FROM agent_sessions WHERE id = %s",
                (session_id,),
            )
        ).fetchone()
        _validate_session(session, sb["id"])

        rows = await (
            await conn.execute(
                "SELECT seq, event_type, payload_json FROM agent_session_events"
                " WHERE session_id = %s AND seq > %s AND event_type = 'message.user'"
                " ORDER BY seq LIMIT 20",
                (session_id, after_seq),
            )
        ).fetchall()
    messages = []
    for r in rows:
        messages.append({
            "seq": r["seq"],
            "type": r["event_type"],
            "data": json.loads(r["payload_json"]) if r["payload_json"] else {},
        })
    return {
        "messages": messages,
        "session_status": session["status"],
    }


# --- Session lifecycle (adapter → Hive) ---


@router.post("/session-update")
async def session_update(body: dict[str, Any], x_sandbox_token: str = Header(...)):
    """Adapter reports session status changes (completed, failed)."""
    sb = await _require_sandbox(x_sandbox_token)
    session_id = body.get("session_id")
    status = body.get("status")
    if not session_id or not isinstance(session_id, str):
        raise HTTPException(400, "session_id required")
    if status not in ("running", "completed", "failed"):
        raise HTTPException(400, "status must be running, completed, or failed")

    async with get_db() as conn:
        session = await (
            await conn.execute(
                "SELECT id, sandbox_id, status FROM agent_sessions WHERE id = %s",
                (session_id,),
            )
        ).fetchone()
        _validate_session(session, sb["id"])
        await conn.execute(
            "UPDATE agent_sessions SET status = %s, updated_at = %s WHERE id = %s",
            (status, now(), session_id),
        )
        await insert_session_event(
            conn, session_id, "session.state.changed", {"state": status},
        )
    return {"status": status}


@router.post("/heartbeat")
async def heartbeat(x_sandbox_token: str = Header(...)):
    """Adapter keep-alive — updates last_active_at."""
    sb = await _require_sandbox(x_sandbox_token)
    async with get_db() as conn:
        await conn.execute(
            "UPDATE task_sandboxes SET last_active_at = %s WHERE id = %s",
            (now(), sb["id"]),
        )
    return {"ok": True}
