"""Shared helpers for sandbox REST handlers."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from .db import now


def new_sandbox_id() -> str:
    return uuid.uuid4().hex


async def append_log_chunk_async(conn, sandbox_id: str, source: str, text: str) -> None:
    ts = now()
    row = await (
        await conn.execute(
            "INSERT INTO sandbox_log_chunks (sandbox_id, seq, source, chunk_text, created_at)"
            " SELECT %s, COALESCE(MAX(seq), -1) + 1, %s, %s, %s FROM sandbox_log_chunks WHERE sandbox_id = %s"
            " RETURNING seq",
            (sandbox_id, source, text, ts, sandbox_id),
        )
    ).fetchone()
    return int(row["seq"])


async def insert_session_event(conn, session_id: str, event_type: str, payload: dict[str, Any]) -> int:
    ts = now()
    row = await (
        await conn.execute(
            "INSERT INTO agent_session_events (session_id, seq, event_type, payload_json, created_at)"
            " SELECT %s, COALESCE(MAX(seq), -1) + 1, %s, %s, %s FROM agent_session_events WHERE session_id = %s"
            " RETURNING seq",
            (session_id, event_type, json.dumps(payload), ts, session_id),
        )
    ).fetchone()
    return int(row["seq"])


async def require_session(conn, session_id: str, task_id: str) -> dict:
    """Load a session row, validating it belongs to the given task. Raises 404."""
    row = await (
        await conn.execute(
            "SELECT s.* FROM agent_sessions s"
            " JOIN task_sandboxes t ON t.id = s.sandbox_id"
            " WHERE s.id = %s AND t.task_id = %s",
            (session_id, task_id),
        )
    ).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    return dict(row)
