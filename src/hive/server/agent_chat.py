"""Agent-chat proxy endpoints.

Hive is a thin, auth-aware proxy in front of rllm-org/agent-sdk. Every endpoint
in this module looks up or creates a row in `agent_chat_sessions` (the
(hive_user, hive_task) → (sdk_session_id, sdk_agent_id, sdk_sandbox_id)
mapping), verifies ownership, then forwards to the agent-sdk REST API via
`AgentSdkClient`. The SSE `/events` endpoint streams the upstream response
bytes straight through to the browser.

All endpoints sit behind `HIVE_AGENT_CHAT=1`. Mounted from main.py only when
the flag is set.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from datetime import datetime
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .agent_sdk_client import get_client
from .db import get_db, now

log = logging.getLogger("hive.agent_chat")

router = APIRouter(prefix="/api")

DEFAULT_AGENT_TYPE = os.environ.get("AGENT_SDK_DEFAULT_AGENT_TYPE", "claude")
DEFAULT_MODEL = os.environ.get("AGENT_SDK_DEFAULT_MODEL", "claude-sonnet-4-6")
DEFAULT_PROVIDER = os.environ.get("AGENT_SDK_DEFAULT_PROVIDER", "daytona")
DEFAULT_CWD = os.environ.get("AGENT_SDK_DEFAULT_CWD", "/home/daytona")


def _require_user():
    from .main import require_user
    return Depends(require_user)


async def _resolve_oauth_token(user_id: int) -> str | None:
    """Fetch the user's stored Claude OAuth token for forwarding to agent-sdk.

    Returns None when the global HIVE_USE_SERVER_KEY toggle is on (caller wants
    the shared server key) or when the user hasn't connected Claude yet. The
    caller should 402 in the latter case — see _require_claude_oauth.
    """
    from .main import _get_user_claude_token, HIVE_USE_SERVER_KEY
    if HIVE_USE_SERVER_KEY:
        return None
    return await _get_user_claude_token(user_id)


async def _require_claude_oauth(user_id: int) -> str | None:
    """Same as _resolve_oauth_token but 402s if the user has no token and
    the server-key override is off. Use on endpoints where we want to force
    the user into the Connect Claude flow instead of silently falling back."""
    from .main import HIVE_USE_SERVER_KEY
    tok = await _resolve_oauth_token(user_id)
    if tok is None and not HIVE_USE_SERVER_KEY:
        raise HTTPException(
            status_code=402,
            detail={"auth_required": True, "reason": "claude_oauth"},
        )
    return tok


async def _check_task_access(owner: str, slug: str, authorization: str) -> None:
    from .main import require_task_access
    await require_task_access(owner, slug, authorization)


async def _resolve_task_id(conn: Any, owner: str, slug: str) -> int:
    row = await (await conn.execute(
        "SELECT id FROM tasks WHERE owner = %s AND slug = %s", (owner, slug)
    )).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    return int(row["id"])


async def _load_owned_session(conn: Any, sid: int, user_id: int) -> dict:
    row = await (await conn.execute(
        "SELECT * FROM agent_chat_sessions WHERE id = %s AND user_id = %s",
        (sid, user_id),
    )).fetchone()
    if not row:
        raise HTTPException(404, "session not found")
    return dict(row)


def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _session_view(row: dict) -> dict:
    from .agent_sdk_client import AGENT_SDK_BASE_URL
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "sdk_session_id": row["sdk_session_id"],
        "sdk_agent_id": row["sdk_agent_id"],
        "sdk_sandbox_id": row["sdk_sandbox_id"],
        "sdk_base_url": AGENT_SDK_BASE_URL,
        "agent_kind": row["agent_kind"],
        "title": row.get("title"),
        "status": row["status"],
        "last_activity": _iso(row.get("last_activity")),
        "created_at": _iso(row["created_at"]),
        "closed_at": _iso(row.get("closed_at")),
    }


# --- session lifecycle ----------------------------------------------------

@router.post("/tasks/{owner}/{slug}/agent-chat/sessions", status_code=201)
async def create_session(
    owner: str,
    slug: str,
    body: dict[str, Any] = Body(default_factory=dict),
    user: dict = _require_user(),
    authorization: str = Header(""),
):
    """Create a new agent-sdk session scoped to this task + user."""
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    agent_kind = (body.get("agent_kind") or DEFAULT_AGENT_TYPE).strip() or DEFAULT_AGENT_TYPE
    title = (body.get("title") or "").strip() or None

    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)

    config: dict[str, Any] = {
        "name": f"hive-{owner}-{slug}-u{user_id}",
        "provider": body.get("provider") or DEFAULT_PROVIDER,
        "agent_type": agent_kind,
        "model": body.get("model") or DEFAULT_MODEL,
        "cwd": body.get("cwd") or DEFAULT_CWD,
    }
    if "prompt" in body:
        config["prompt"] = body["prompt"]
    if "tools" in body:
        config["tools"] = body["tools"]
    if "mcp_servers" in body:
        config["mcp_servers"] = body["mcp_servers"]
    if "skills" in body:
        config["skills"] = body["skills"]
    if "agent_command" in body:
        config["agent_command"] = body["agent_command"]

    client = get_client()
    upstream = await client.create_quick_session(**config)
    sdk_session_id = upstream.get("session_id")
    sdk_agent_id = upstream.get("agent_id")
    sdk_sandbox_id = upstream.get("sandbox_id")
    if not (sdk_session_id and sdk_agent_id and sdk_sandbox_id):
        raise HTTPException(502, f"agent-sdk returned incomplete session: {upstream}")

    async with get_db() as conn:
        created = now()
        row = await (await conn.execute(
            "INSERT INTO agent_chat_sessions"
            " (user_id, task_id, sdk_session_id, sdk_agent_id, sdk_sandbox_id,"
            "  agent_kind, title, status, last_activity, created_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)"
            " RETURNING *",
            (user_id, task_id, sdk_session_id, sdk_agent_id, sdk_sandbox_id,
             agent_kind, title, created, created),
        )).fetchone()

    from fastapi.responses import JSONResponse
    return JSONResponse(_session_view(dict(row)), status_code=201)


@router.get("/tasks/{owner}/{slug}/agent-chat/sessions")
async def list_sessions(
    owner: str,
    slug: str,
    user: dict = _require_user(),
    authorization: str = Header(""),
):
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)
        rows = await (await conn.execute(
            "SELECT * FROM agent_chat_sessions"
            " WHERE user_id = %s AND task_id = %s"
            " ORDER BY created_at DESC",
            (user_id, task_id),
        )).fetchall()
    return {"sessions": [_session_view(dict(r)) for r in rows]}


@router.get("/agent-chat/sessions/{sid}")
async def get_session(sid: int, user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
    tok = await _resolve_oauth_token(user_id)
    upstream: dict[str, Any] = {}
    try:
        upstream = await get_client().get_status(row["sdk_session_id"], oauth_token=tok)
    except HTTPException as e:
        log.warning("get_status failed for sdk_session_id=%s: %s", row["sdk_session_id"], e.detail)
    view = _session_view(row)
    view["upstream_status"] = upstream
    return view


@router.get("/agent-chat/sessions/{sid}/log")
async def get_log(sid: int, limit: int = Query(500, ge=1, le=2000), user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
    tok = await _resolve_oauth_token(user_id)
    events = await get_client().get_log(row["sdk_session_id"], limit=limit, oauth_token=tok)
    return {"events": events}


@router.get("/agent-chat/sessions/{sid}/events")
async def stream_events(sid: int, request: Request, user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)

    tok = await _resolve_oauth_token(user_id)
    client = get_client()
    sdk_sid = row["sdk_session_id"]

    async def gen():
        try:
            async for chunk in client.stream_events(sdk_sid, oauth_token=tok):
                if await request.is_disconnected():
                    break
                yield chunk
        except Exception as e:
            log.warning("SSE stream aborted for sdk_session_id=%s: %s", sdk_sid, e)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@router.post("/agent-chat/sessions/{sid}/message")
async def send_message(
    sid: int,
    body: dict[str, Any] = Body(...),
    user: dict = _require_user(),
):
    text = (body.get("text") or body.get("message") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    interrupt = bool(body.get("interrupt"))

    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)

    tok = await _require_claude_oauth(user_id)
    result = await get_client().send_message(row["sdk_session_id"], text, interrupt=interrupt, oauth_token=tok)

    async with get_db() as conn:
        await conn.execute(
            "UPDATE agent_chat_sessions SET last_activity = %s WHERE id = %s",
            (now(), sid),
        )
    return result


@router.post("/agent-chat/sessions/{sid}/cancel")
async def cancel(sid: int, user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
    tok = await _resolve_oauth_token(user_id)
    return await get_client().cancel(row["sdk_session_id"], oauth_token=tok)


@router.post("/agent-chat/sessions/{sid}/resume")
async def resume(sid: int, user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
    tok = await _require_claude_oauth(user_id)
    return await get_client().resume(row["sdk_session_id"], oauth_token=tok)


@router.post("/agent-chat/sessions/{sid}/config")
async def set_config(sid: int, body: dict[str, Any] = Body(...), user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
    tok = await _resolve_oauth_token(user_id)
    return await get_client().set_config(row["sdk_session_id"], oauth_token=tok, **body)


@router.delete("/agent-chat/sessions/{sid}", status_code=204)
async def close_session(sid: int, user: dict = _require_user()):
    user_id = int(user["sub"])
    async with get_db() as conn:
        row = await _load_owned_session(conn, sid, user_id)
        if row["status"] == "closed":
            return None
    await get_client().destroy_sandbox(row["sdk_sandbox_id"])
    async with get_db() as conn:
        await conn.execute(
            "UPDATE agent_chat_sessions SET status = 'closed', closed_at = %s WHERE id = %s",
            (now(), sid),
        )
    return None
