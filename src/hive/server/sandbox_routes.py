"""REST + SSE APIs for private-task Daytona sandboxes and agent sessions."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import traceback
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from .daytona_runtime import AsyncDaytona, create_sandbox_interactive
from .db import get_db, now, paginate
from .sandbox_agent_connections import load_provider_credential, router as agent_connections_router
from .sandbox_contract import SessionLaunchSpec, normalize_approval_mode, normalize_provider
from .sandbox_helpers import append_log_chunk_async, insert_session_event, new_sandbox_id, require_session

log = logging.getLogger("hive.sandbox")

router = APIRouter(prefix="/api")
router.include_router(agent_connections_router)


async def _require_private_task_owner(task_id: str, authorization: str = Header("")) -> dict:
    from . import main as main_mod

    uid = await main_mod._get_user_id_from_auth(authorization)
    if not uid:
        raise HTTPException(401, "authentication required")
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT id, visibility, owner_id, task_type FROM tasks WHERE id = %s",
                (task_id,),
            )
        ).fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        if row["visibility"] != "private" or row.get("task_type") != "private":
            raise HTTPException(400, "sandbox is only available for private tasks")
        if row["owner_id"] != uid:
            raise HTTPException(403, "task owner access required")
        return dict(row)


# --- Sandbox lifecycle ---


@router.post("/tasks/{task_id}/sandbox")
async def ensure_sandbox(task_id: str, body: dict[str, Any], authorization: str = Header("")):
    task_row = await _require_private_task_owner(task_id, authorization)
    uid = task_row["owner_id"]
    try:
        provider = normalize_provider(body.get("provider", "claude_code"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    snapshot = body.get("snapshot") or None

    # Return existing sandbox if it's already alive.
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT * FROM task_sandboxes WHERE task_id = %s", (task_id,))
        ).fetchone()
        if row and row["status"] in ("ready", "running"):
            await conn.execute(
                "UPDATE task_sandboxes SET last_active_at = %s WHERE id = %s",
                (now(), row["id"]),
            )
            return {"sandbox_id": row["id"], "status": row["status"], "task_id": task_id, "provider": row["provider"]}

    # Create or recycle the sandbox row, then provision Daytona inline.
    sid = None
    async with get_db() as conn:
        ts = now()
        if row:
            sid = row["id"]
            await conn.execute(
                "UPDATE task_sandboxes SET status = %s, provider = %s, snapshot = COALESCE(%s, snapshot),"
                " error_message = NULL, last_active_at = %s WHERE id = %s",
                ("starting", provider, snapshot, ts, sid),
            )
        else:
            sid = new_sandbox_id()
            await conn.execute(
                """INSERT INTO task_sandboxes
                   (id, task_id, owner_id, provider, status, snapshot, created_at, last_active_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (sid, task_id, uid, provider, "starting", snapshot, ts, ts),
            )
        await append_log_chunk_async(conn, sid, "system", f"sandbox ensure requested provider={provider}\n")

    # Provision Daytona sandbox synchronously — the user is waiting.
    if not os.environ.get("DAYTONA_API_KEY"):
        async with get_db() as conn:
            await conn.execute(
                "UPDATE task_sandboxes SET status = %s, error_message = %s WHERE id = %s",
                ("failed", "DAYTONA_API_KEY not configured", sid),
            )
        raise HTTPException(503, "sandbox provisioning not available (DAYTONA_API_KEY not set)")

    adapter_token = secrets.token_urlsafe(32)
    server_url = os.environ.get("HIVE_SERVER_URL", "").rstrip("/")

    # Load the user's provider credential and inject it into the sandbox.
    provider_credential = await load_provider_credential(uid, provider)
    try:
        async with AsyncDaytona() as daytona:
            adapter_env = {
                "HIVE_SERVER_URL": server_url,
                "HIVE_ADAPTER_TOKEN": adapter_token,
                "HIVE_SANDBOX_ID": sid,
                "HIVE_PROVIDER": provider,
            }
            if provider == "claude_code" and provider_credential:
                adapter_env["ANTHROPIC_API_KEY"] = provider_credential
            elif provider == "codex" and provider_credential:
                adapter_env["OPENAI_API_KEY"] = provider_credential
            elif provider_credential:
                adapter_env["PROVIDER_API_KEY"] = provider_credential
            box = await create_sandbox_interactive(daytona, snapshot=snapshot, env_vars=adapter_env)
            did = getattr(box, "id", None) or str(box)
            ts = now()
            async with get_db() as conn:
                await conn.execute(
                    "UPDATE task_sandboxes SET status = %s, daytona_sandbox_id = %s,"
                    " adapter_token = %s, last_active_at = %s, error_message = NULL WHERE id = %s",
                    ("ready", str(did), adapter_token, ts, sid),
                )
                await append_log_chunk_async(conn, sid, "system", f"Daytona sandbox ready id={did}\n")
        log.info("sandbox %s ready (%s)", sid, did)
        return {"sandbox_id": sid, "status": "ready", "task_id": task_id, "provider": provider}
    except Exception as exc:
        log.exception("sandbox %s failed", sid)
        err = f"{exc}\n{traceback.format_exc()}"
        async with get_db() as conn:
            await conn.execute(
                "UPDATE task_sandboxes SET status = %s, error_message = %s, last_active_at = %s WHERE id = %s",
                ("failed", err[:2000], now(), sid),
            )
            await append_log_chunk_async(conn, sid, "system", f"provision error: {err}\n")
        raise HTTPException(502, "sandbox provisioning failed") from exc


@router.get("/tasks/{task_id}/sandbox")
async def get_sandbox(task_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        row = await (
            await conn.execute("SELECT * FROM task_sandboxes WHERE task_id = %s", (task_id,))
        ).fetchone()
    if not row:
        return {"sandbox": None}
    return {"sandbox": dict(row)}


@router.post("/tasks/{task_id}/sandbox/stop")
async def stop_sandbox(task_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT id, daytona_sandbox_id FROM task_sandboxes WHERE task_id = %s",
                (task_id,),
            )
        ).fetchone()
    if not row:
        raise HTTPException(404, "no sandbox for task")
    sid = row["id"]
    daytona_id = row["daytona_sandbox_id"]

    # Stop the Daytona sandbox if it was provisioned.
    if daytona_id and os.environ.get("DAYTONA_API_KEY"):
        try:
            async with AsyncDaytona() as daytona:
                sandbox = await daytona.get(daytona_id)
                await daytona.stop(sandbox, timeout=60)
        except Exception:
            log.warning("failed to stop Daytona sandbox %s for %s", daytona_id, sid)

    ts = now()
    async with get_db() as conn:
        await conn.execute(
            "UPDATE task_sandboxes SET status = %s, stopped_at = %s WHERE id = %s",
            ("stopped", ts, sid),
        )
        await append_log_chunk_async(conn, sid, "system", "sandbox stopped\n")
    return {"status": "stopped"}


@router.delete("/tasks/{task_id}/sandbox")
async def delete_sandbox(task_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        row = await (
            await conn.execute("DELETE FROM task_sandboxes WHERE task_id = %s RETURNING id", (task_id,))
        ).fetchone()
    if not row:
        raise HTTPException(404, "no sandbox for task")
    return {"status": "deleted"}


# --- Sessions ---


@router.post("/tasks/{task_id}/sandbox/sessions")
async def create_session(task_id: str, body: dict[str, Any], authorization: str = Header("")):
    task_row = await _require_private_task_owner(task_id, authorization)
    uid = task_row["owner_id"]
    async with get_db() as conn:
        sb = await (
            await conn.execute("SELECT id FROM task_sandboxes WHERE task_id = %s", (task_id,))
        ).fetchone()
        if not sb:
            raise HTTPException(400, f"create sandbox first: POST /tasks/{task_id}/sandbox")
        try:
            prov = normalize_provider(body.get("provider", "claude_code"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    # Validate that the user has a connected provider credential.
    cred = await load_provider_credential(uid, prov)
    if not cred and not body.get("skip_credential_check"):
        async with get_db() as conn:
            conn_row = await (
                await conn.execute(
                    "SELECT status FROM user_agent_connections WHERE user_id = %s AND provider = %s",
                    (uid, prov),
                )
            ).fetchone()
            status = conn_row["status"] if conn_row else "not_found"
            raise HTTPException(
                400,
                f"{prov} not connected (status: {status}). "
                f"Connect first: POST /users/me/agent-connections/{prov}/begin",
            )

    async with get_db() as conn:
        try:
            approval = normalize_approval_mode(body.get("approval_mode", "guarded"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        cwd = body.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise HTTPException(400, "cwd must be a string")
        po = body.get("provider_options") if isinstance(body.get("provider_options"), dict) else {}
        spec = SessionLaunchSpec(provider=prov, approval_mode=approval, cwd=cwd, provider_options=po)
        extra = spec.cli_extra_args()
        sid = new_sandbox_id()
        ts = now()
        await conn.execute(
            """INSERT INTO agent_sessions
               (id, sandbox_id, title, status, cwd, approval_mode, provider_options_json, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                sid,
                sb["id"],
                body.get("title"),
                "running",
                cwd,
                approval,
                json.dumps({"provider": prov, "cli_extra_args": extra, "provider_options": po}),
                ts,
                ts,
            ),
        )
        await insert_session_event(conn, sid, "session.started", {"provider": prov, "approval_mode": approval, "cli_extra_args": extra})
    return {
        "session_id": sid,
        "provider": prov,
        "approval_mode": approval,
        "cli_extra_args": extra,
    }


@router.get("/tasks/{task_id}/sandbox/sessions/{session_id}")
async def get_session(task_id: str, session_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        return await require_session(conn, session_id, task_id)


@router.post("/tasks/{task_id}/sandbox/sessions/{session_id}/messages")
async def post_message(task_id: str, session_id: str, body: dict[str, Any], authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    msg = body.get("message") or body.get("content")
    if not msg or not isinstance(msg, str):
        raise HTTPException(400, "message required")
    async with get_db() as conn:
        await require_session(conn, session_id, task_id)
        await insert_session_event(conn, session_id, "message.user", {"text": msg})
        await conn.execute("UPDATE agent_sessions SET updated_at = %s WHERE id = %s", (now(), session_id))
    return {"status": "ok", "session_id": session_id}


@router.post("/tasks/{task_id}/sandbox/sessions/{session_id}/interrupt")
async def interrupt_session(task_id: str, session_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        await require_session(conn, session_id, task_id)
        await insert_session_event(conn, session_id, "session.state.changed", {"state": "interrupted"})
        await conn.execute("UPDATE agent_sessions SET status = %s, updated_at = %s WHERE id = %s", ("interrupted", now(), session_id))
    return {"status": "interrupted"}


@router.post("/tasks/{task_id}/sandbox/sessions/{session_id}/permissions")
async def resolve_permission(task_id: str, session_id: str, body: dict[str, Any], authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    approved = bool(body.get("approved", False))
    async with get_db() as conn:
        await require_session(conn, session_id, task_id)
        await insert_session_event(conn, session_id, "permission.resolved", {"approved": approved, "request_id": body.get("request_id")})
    return {"status": "ok", "approved": approved}


@router.get("/tasks/{task_id}/sandbox/sessions/{session_id}/events")
async def list_events(
    task_id: str,
    session_id: str,
    authorization: str = Header(""),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        await require_session(conn, session_id, task_id)
        rows = await (
            await conn.execute(
                "SELECT seq, event_type, payload_json, created_at FROM agent_session_events"
                " WHERE session_id = %s AND seq >= %s ORDER BY seq LIMIT %s",
                (session_id, offset, limit),
            )
        ).fetchall()
    events = [
        {
            "offset": r["seq"],
            "type": r["event_type"],
            "data": json.loads(r["payload_json"]) if r["payload_json"] else {},
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    next_offset = (events[-1]["offset"] + 1) if events else offset
    return {"events": events, "next_offset": next_offset}


@router.get("/tasks/{task_id}/sandbox/sessions/{session_id}/stream")
async def stream_events(task_id: str, session_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)

    async def gen() -> AsyncIterator[bytes]:
        last = 0
        while True:
            async with get_db() as conn:
                row = await (
                    await conn.execute(
                        "SELECT s.id, s.status FROM agent_sessions s"
                        " JOIN task_sandboxes t ON t.id = s.sandbox_id"
                        " WHERE s.id = %s AND t.task_id = %s",
                        (session_id, task_id),
                    )
                ).fetchone()
                if not row:
                    yield b"event: error\ndata: {\"error\":\"session not found\"}\n\n"
                    return
                rows = await (
                    await conn.execute(
                        "SELECT seq, event_type, payload_json FROM agent_session_events"
                        " WHERE session_id = %s AND seq >= %s ORDER BY seq LIMIT 50",
                        (session_id, last),
                    )
                ).fetchall()
            for r in rows:
                last = r["seq"] + 1
                payload = {
                    "offset": r["seq"],
                    "type": r["event_type"],
                    "data": json.loads(r["payload_json"]) if r["payload_json"] else {},
                }
                yield f"data: {json.dumps(payload)}\n\n".encode()
            if row["status"] in ("completed", "failed", "interrupted"):
                yield b"event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/tasks/{task_id}/sandbox/logs")
async def sandbox_logs(
    task_id: str,
    authorization: str = Header(""),
    page: int = Query(1),
    per_page: int = Query(50),
):
    await _require_private_task_owner(task_id, authorization)
    page, per_page, sql_offset = paginate(page, per_page)
    async with get_db() as conn:
        sb = await (
            await conn.execute("SELECT id FROM task_sandboxes WHERE task_id = %s", (task_id,))
        ).fetchone()
        if not sb:
            return {"chunks": [], "page": page, "per_page": per_page, "has_next": False}
        rows = await (
            await conn.execute(
                "SELECT seq, source, chunk_text, created_at FROM sandbox_log_chunks"
                " WHERE sandbox_id = %s ORDER BY seq DESC LIMIT %s OFFSET %s",
                (sb["id"], per_page + 1, sql_offset),
            )
        ).fetchall()
    has_next = len(rows) > per_page
    rows = rows[:per_page]
    chunks = [
        {
            "seq": r["seq"],
            "source": r["source"],
            "text": r["chunk_text"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]
    return {"chunks": chunks, "page": page, "per_page": per_page, "has_next": has_next}


@router.get("/tasks/{task_id}/sandbox/sessions/{session_id}/transcript")
async def session_transcript(task_id: str, session_id: str, authorization: str = Header("")):
    await _require_private_task_owner(task_id, authorization)
    async with get_db() as conn:
        await require_session(conn, session_id, task_id)
        rows = await (
            await conn.execute(
                "SELECT seq, event_type, payload_json FROM agent_session_events"
                " WHERE session_id = %s ORDER BY seq", (session_id,),
            )
        ).fetchall()
    return {"transcript": [
        {"offset": r["seq"], "type": r["event_type"], "data": json.loads(r["payload_json"]) if r["payload_json"] else {}}
        for r in rows
    ]}
