"""WebSocket terminal proxy: PTY over SSH into the user's Daytona sandbox.

Sessions persist across WebSocket disconnects. When the user closes the modal,
the SSH channel stays alive. Reopening the modal and clicking the session
mints a fresh ticket and reattaches.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import secrets
import socket
import threading
import time as _time
from datetime import timedelta
from typing import Annotated, Any

import paramiko
from fastapi import APIRouter, Body, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from .db import get_db, now
from .sandbox import AsyncDaytona, _encrypt

log = logging.getLogger("hive.sandbox_terminal")

router = APIRouter(prefix="/api")

TERMINAL_TICKET_TTL_SEC = int(os.environ.get("TERMINAL_TICKET_TTL_SEC", "120"))
SANDBOX_SSH_EXPIRES_MINUTES = int(os.environ.get("SANDBOX_SSH_EXPIRES_MINUTES", "480"))
TASK_DIR = "/home/daytona"

# ── Persistent SSH session pool ──────────────────────────────────────────────
# Keyed by session_id. Survives WebSocket disconnects so users can reattach.

class _SshSession:
    __slots__ = ("transport", "chan", "stop_ev", "session_id", "last_ws_time")

    def __init__(self, transport: paramiko.Transport, chan: paramiko.Channel, session_id: int):
        self.transport = transport
        self.chan = chan
        self.stop_ev = threading.Event()
        self.session_id = session_id
        self.last_ws_time = _time.monotonic()

    def alive(self) -> bool:
        return self.transport.is_active() and not self.chan.closed

    def close(self):
        self.stop_ev.set()
        try:
            self.chan.close()
        except Exception:
            pass
        try:
            self.transport.close()
        except Exception:
            pass


_pool: dict[int, _SshSession] = {}
_pool_lock = threading.Lock()


def _pool_put(session_id: int, ssh: _SshSession) -> None:
    with _pool_lock:
        _pool[session_id] = ssh


def _pool_get(session_id: int) -> _SshSession | None:
    with _pool_lock:
        ssh = _pool.get(session_id)
    if ssh and ssh.alive():
        return ssh
    if ssh:
        ssh.close()
        with _pool_lock:
            _pool.pop(session_id, None)
    return None


def _pool_remove(session_id: int) -> None:
    with _pool_lock:
        ssh = _pool.pop(session_id, None)
    if ssh:
        ssh.close()


def signal_session_stop(session_id: int) -> None:
    _pool_remove(session_id)


async def stop_all_terminal_sessions_for_sandbox(sandbox_id: int) -> None:
    async with get_db() as conn:
        rows = await (await conn.execute(
            "SELECT id FROM sandbox_terminal_sessions WHERE sandbox_id = %s AND closed_at IS NULL",
            (sandbox_id,),
        )).fetchall()
    for r in rows:
        signal_session_stop(r["id"])


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _check_task_access(owner: str, slug: str, authorization: str):
    from .main import require_task_access
    await require_task_access(owner, slug, authorization)


async def _resolve_task_id(conn: Any, owner: str, slug: str) -> int:
    """Look up a task by owner+slug and return the integer task id."""
    row = await (await conn.execute(
        "SELECT id FROM tasks WHERE owner = %s AND slug = %s",
        (owner, slug),
    )).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    return row["id"]


def _parse_ssh_command(cmd: str) -> tuple[str, int, str]:
    if not cmd or not cmd.strip().startswith("ssh"):
        raise ValueError("unsupported ssh command")
    port = 22
    m = re.search(r"-p\s+(\d+)", cmd)
    if m:
        port = int(m.group(1))
    m = re.search(r"(\S+)@(\S+)", cmd)
    if not m:
        raise ValueError("could not parse ssh user@host")
    user, host = m.group(1), m.group(2)
    host = host.rstrip(",").strip("\"'")
    for suf in (":", "/"):
        if host.endswith(suf):
            host = host[:-1]
    return host, port, user


async def _load_sandbox_ready(task_id: int, user_id: int) -> dict:
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT * FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "no sandbox for this task")
        row = dict(row)
        if row["status"] != "ready":
            raise HTTPException(409, "sandbox is not ready")
        if (
            row.get("ssh_expires_at")
            and row["ssh_expires_at"] < now()
            and row.get("daytona_sandbox_id")
        ):
            try:
                async with AsyncDaytona() as daytona:
                    sandbox = await daytona.get(row["daytona_sandbox_id"])
                    ssh = await sandbox.create_ssh_access(expires_in_minutes=SANDBOX_SSH_EXPIRES_MINUTES)
                    await conn.execute(
                        "UPDATE sandboxes SET ssh_command = %s, ssh_token = %s,"
                        " ssh_expires_at = %s, last_accessed_at = %s WHERE id = %s",
                        (ssh.ssh_command, _encrypt(ssh.token), ssh.expires_at, now(), row["id"]),
                    )
                    row["ssh_command"] = ssh.ssh_command
                    row["ssh_token"] = _encrypt(ssh.token)
                    row["ssh_expires_at"] = ssh.expires_at
            except Exception as exc:
                log.warning("SSH refresh failed: %s", exc)
                raise HTTPException(502, "could not refresh sandbox SSH access") from exc
        return row


def _mint_ticket() -> tuple[str, Any]:
    ticket = secrets.token_urlsafe(32)
    exp = now() + timedelta(seconds=TERMINAL_TICKET_TTL_SEC)
    return ticket, exp


# ── REST endpoints ───────────────────────────────────────────────────────────

@router.get("/tasks/{owner}/{slug}/sandbox/sessions")
async def list_terminal_sessions(owner: str, slug: str, authorization: str = Header("")):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)
        sb = await (await conn.execute(
            "SELECT id FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()
        if not sb:
            raise HTTPException(404, "no sandbox for this task")
        rows = await (await conn.execute(
            "SELECT id, title, created_at, last_activity_at, closed_at"
            " FROM sandbox_terminal_sessions WHERE sandbox_id = %s AND closed_at IS NULL"
            " ORDER BY created_at",
            (sb["id"],),
        )).fetchall()
    sessions = []
    for r in rows:
        d = dict(r)
        d["connected"] = _pool_get(r["id"]) is not None
        sessions.append(d)
    return {"sessions": sessions}


@router.post("/tasks/{owner}/{slug}/sandbox/sessions", status_code=201)
async def create_terminal_session(
    owner: str,
    slug: str,
    body: Annotated[dict[str, Any] | None, Body()] = None,
    authorization: str = Header(""),
):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    title = (body or {}).get("title")
    if title is not None and not isinstance(title, str):
        raise HTTPException(400, "title must be a string")
    if isinstance(title, str) and len(title) > 200:
        raise HTTPException(400, "title too long")

    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)

    await _load_sandbox_ready(task_id, user_id)
    ticket, exp = _mint_ticket()

    async with get_db() as conn:
        sb = await (await conn.execute(
            "SELECT id FROM sandboxes WHERE task_id = %s AND user_id = %s",
            (task_id, user_id),
        )).fetchone()
        if not sb:
            raise HTTPException(404, "no sandbox for this task")
        row = await (await conn.execute(
            "INSERT INTO sandbox_terminal_sessions"
            " (sandbox_id, user_id, title, connect_ticket, connect_ticket_expires_at, created_at, last_activity_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (sb["id"], user_id, title, ticket, exp, now(), now()),
        )).fetchone()
        sid = row["id"]

    return JSONResponse(
        {"id": sid, "title": title, "ticket": ticket, "ticket_expires_at": exp.isoformat()},
        status_code=201,
    )


@router.post("/tasks/{owner}/{slug}/sandbox/sessions/{session_id}/ticket", status_code=201)
async def reconnect_ticket(
    owner: str,
    slug: str,
    session_id: int,
    authorization: str = Header(""),
):
    """Mint a fresh connect ticket for an existing (open) session."""
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    ticket, exp = _mint_ticket()
    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)
        row = await (await conn.execute(
            "SELECT s.id FROM sandbox_terminal_sessions s"
            " JOIN sandboxes b ON b.id = s.sandbox_id"
            " WHERE s.id = %s AND b.task_id = %s AND b.user_id = %s AND s.closed_at IS NULL",
            (session_id, task_id, user_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "session not found or closed")
        await conn.execute(
            "UPDATE sandbox_terminal_sessions SET connect_ticket = %s, connect_ticket_expires_at = %s WHERE id = %s",
            (ticket, exp, session_id),
        )
    return JSONResponse(
        {"ticket": ticket, "ticket_expires_at": exp.isoformat()},
        status_code=201,
    )


@router.delete("/tasks/{owner}/{slug}/sandbox/sessions/{session_id}")
async def delete_terminal_session(
    owner: str,
    slug: str,
    session_id: int,
    authorization: str = Header(""),
):
    from .main import require_user as _require_user_fn
    user = await _require_user_fn(authorization)
    await _check_task_access(owner, slug, authorization)
    user_id = int(user["sub"])
    async with get_db() as conn:
        task_id = await _resolve_task_id(conn, owner, slug)
        row = await (await conn.execute(
            "SELECT s.id, s.user_id FROM sandbox_terminal_sessions s"
            " JOIN sandboxes b ON b.id = s.sandbox_id"
            " WHERE s.id = %s AND b.task_id = %s AND b.user_id = %s",
            (session_id, task_id, user_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "session not found")
        signal_session_stop(session_id)
        await conn.execute(
            "UPDATE sandbox_terminal_sessions SET closed_at = %s WHERE id = %s",
            (now(), session_id),
        )
    return {"status": "closed", "id": session_id}


# ── WebSocket terminal ───────────────────────────────────────────────────────

@router.websocket("/tasks/{owner}/{slug}/sandbox/terminal/ws")
async def terminal_websocket(
    websocket: WebSocket,
    owner: str,
    slug: str,
    ticket: str = Query(...),
):
    try:
        row = await _validate_ticket_and_load(owner, slug, ticket)
    except HTTPException:
        await websocket.close(code=4403)
        return
    except Exception:
        await websocket.close(code=4403)
        return

    await websocket.accept()

    session_id = row["session_id"]
    ssh_cmd = row["ssh_command"]

    try:
        host, port, username = _parse_ssh_command(ssh_cmd)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close(code=1011)
        return

    # Try to reattach to an existing SSH session
    ssh = _pool_get(session_id)
    if ssh:
        log.info("Reattaching WS to existing SSH session %s", session_id)
    else:
        # Create new SSH connection
        def _ssh_connect():
            t = paramiko.Transport((host, port))
            t.connect(username=username)
            t.auth_none(username)
            ch = t.open_session()
            ch.get_pty(term="xterm", width=80, height=24)
            ch.invoke_shell()
            # cd to task directory
            ch.send(f"export NVM_DIR=/usr/local/share/nvm && . $NVM_DIR/nvm.sh 2>/dev/null; export HIVE_SERVER=https://hive.rllm-project.com; cd {TASK_DIR} 2>/dev/null; clear\n".encode())
            return t, ch

        try:
            transport, chan = await asyncio.to_thread(_ssh_connect)
        except Exception as e:
            log.exception("SSH connect failed for session %s", session_id)
            await websocket.send_json({"type": "error", "message": f"ssh failed: {e}"})
            await websocket.close(code=1011)
            async with get_db() as conn:
                await conn.execute(
                    "UPDATE sandbox_terminal_sessions SET closed_at = %s WHERE id = %s",
                    (now(), session_id),
                )
            return
        ssh = _SshSession(transport, chan, session_id)
        _pool_put(session_id, ssh)

    chan = ssh.chan
    chan.settimeout(0.25)
    ssh.stop_ev.clear()
    ssh.last_ws_time = _time.monotonic()

    recv_task: asyncio.Task | None = None

    async def pump_out() -> None:
        while not ssh.stop_ev.is_set():
            try:
                data = await asyncio.to_thread(chan.recv, 65536)
            except socket.timeout:
                continue
            except Exception:
                break
            if not data:
                break
            try:
                await websocket.send_json(
                    {"type": "output", "data": base64.b64encode(data).decode("ascii")}
                )
            except Exception:
                break

    recv_task = asyncio.create_task(pump_out())

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            mtype = msg.get("type")
            if mtype == "input" and "data" in msg:
                try:
                    chan.send(base64.b64decode(msg["data"]))
                except Exception:
                    break
            elif mtype == "resize":
                cols = max(20, min(int(msg.get("cols", 80)), 500))
                rows = max(5, min(int(msg.get("rows", 24)), 200))
                try:
                    chan.resize_pty(width=cols, height=rows)
                except Exception:
                    pass
            elif mtype == "ping":
                await websocket.send_json({"type": "pong"})
            ssh.last_ws_time = _time.monotonic()
    finally:
        # WS disconnected — detach but keep SSH alive for reconnect
        ssh.stop_ev.set()
        if recv_task:
            recv_task.cancel()
            try:
                await recv_task
            except asyncio.CancelledError:
                pass
        # Do NOT close transport/chan — they stay in the pool
        log.info("WS detached from session %s, SSH stays alive", session_id)
        async with get_db() as conn:
            await conn.execute(
                "UPDATE sandbox_terminal_sessions SET last_activity_at = %s WHERE id = %s",
                (now(), session_id),
            )


async def _validate_ticket_and_load(owner: str, slug: str, ticket: str) -> dict[str, Any]:
    async with get_db() as conn:
        row = await (await conn.execute(
            "SELECT s.id AS session_id, s.sandbox_id, s.user_id, s.connect_ticket_expires_at,"
            " b.ssh_command, b.ssh_token, b.status, t.id AS task_id"
            " FROM sandbox_terminal_sessions s"
            " JOIN sandboxes b ON b.id = s.sandbox_id"
            " JOIN tasks t ON t.id = b.task_id"
            " WHERE t.owner = %s AND t.slug = %s AND s.connect_ticket = %s AND s.closed_at IS NULL",
            (owner, slug, ticket),
        )).fetchone()
        if not row:
            raise HTTPException(404, "invalid or expired ticket")
        if row["connect_ticket_expires_at"] and row["connect_ticket_expires_at"] < now():
            raise HTTPException(404, "invalid or expired ticket")
        if row["status"] != "ready":
            raise HTTPException(409, "sandbox not ready")

        sb_row = await (await conn.execute(
            "SELECT * FROM sandboxes WHERE id = %s", (row["sandbox_id"],)
        )).fetchone()
        if not sb_row:
            raise HTTPException(404, "sandbox missing")
        sb_row = dict(sb_row)
        if (
            sb_row.get("ssh_expires_at")
            and sb_row["ssh_expires_at"] < now()
            and sb_row.get("daytona_sandbox_id")
        ):
            async with AsyncDaytona() as daytona:
                sandbox = await daytona.get(sb_row["daytona_sandbox_id"])
                ssh = await sandbox.create_ssh_access(expires_in_minutes=SANDBOX_SSH_EXPIRES_MINUTES)
                await conn.execute(
                    "UPDATE sandboxes SET ssh_command = %s, ssh_token = %s,"
                    " ssh_expires_at = %s, last_activity_at = %s WHERE id = %s",
                    (ssh.ssh_command, _encrypt(ssh.token), ssh.expires_at, now(), sb_row["id"]),
                )
                sb_row["ssh_command"] = ssh.ssh_command
                sb_row["ssh_token"] = _encrypt(ssh.token)

        return {
            "session_id": row["session_id"],
            "ssh_command": sb_row["ssh_command"],
        }
