import asyncio
import json
import logging
import re
import time
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import get_db, now
from .mentions import mentions_for_message

log = logging.getLogger("hive.channels")


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            default=lambda o: o.isoformat() if isinstance(o, datetime) else (_ for _ in ()).throw(TypeError),
        ).encode("utf-8")


_CHANNEL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,20}$")

# Default channel auto-created for every task. Reserved name (cannot be re-created).
DEFAULT_CHANNEL = "general"


def _validate_channel_name(name: str) -> None:
    if not isinstance(name, str) or not _CHANNEL_NAME_RE.match(name):
        raise HTTPException(
            400,
            "channel name must be 1-21 chars, lowercase letters/digits/hyphens, must start with letter or digit",
        )


def _validate_text(text: str) -> None:
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(400, "text is required and cannot be blank")
    if "\x00" in text:
        raise HTTPException(400, "text must not contain null bytes")
    if len(text) > 8000:
        raise HTTPException(400, "text max 8000 chars")


async def _get_agent(token: str, x_agent_token: str, conn) -> str:
    effective = x_agent_token or token
    if not effective:
        raise HTTPException(401, "authentication required")
    row = await (await conn.execute("SELECT id FROM agents WHERE token = %s", (effective,))).fetchone()
    if not row:
        row = await (await conn.execute("SELECT id FROM agents WHERE id = %s", (effective,))).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), row["id"]))
    return row["id"]


async def _resolve_author(
    token: str,
    x_agent_token: str,
    authorization: str,
    conn,
    x_agent_harness: str = "",
    x_agent_model: str = "",
) -> tuple[str, str | int]:
    """Authenticate the caller as either an agent or a user.

    Returns ('agent', agent_id) or ('user', user_id). Agent token takes
    precedence so the CLI keeps working unchanged. If X-Agent-Harness /
    X-Agent-Model headers are present, updates the agent's harness/model
    fields (auto-detection from the CLI).
    """
    # Try agent token first (CLI flow)
    effective = x_agent_token or token
    if effective:
        row = await (await conn.execute(
            "SELECT id FROM agents WHERE token = %s OR id = %s", (effective, effective)
        )).fetchone()
        if row:
            # Update last_seen + harness/model from auto-detection headers
            if x_agent_harness:
                await conn.execute(
                    "UPDATE agents SET last_seen_at = %s, harness = %s, model = %s WHERE id = %s",
                    (now(), x_agent_harness, x_agent_model or "unknown", row["id"]),
                )
            else:
                await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), row["id"]))
            return ("agent", row["id"])
    # Try user auth header (UI flow)
    if authorization:
        # Function-level import to avoid circular dependency at module load
        from .main import _get_user_id_from_auth
        user_id = await _get_user_id_from_auth(authorization)
        if user_id is not None:
            return ("user", user_id)
    raise HTTPException(401, "authentication required")


async def _resolve_task_id(owner: str, slug: str, conn) -> int:
    row = await (await conn.execute(
        "SELECT id FROM tasks WHERE owner = %s AND slug = %s", (owner, slug)
    )).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    return row["id"]


async def _resolve_channel(task_id: int, name: str, conn) -> dict:
    row = await (await conn.execute(
        "SELECT * FROM channels WHERE task_id = %s AND name = %s", (task_id, name)
    )).fetchone()
    if not row:
        raise HTTPException(404, f"channel '{name}' not found")
    return dict(row)


def _channel_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "name": row["name"],
        "is_default": row["is_default"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
    }


async def _ensure_default_channels(task_id: int, agent_id: str | None, conn) -> None:
    """Idempotently create the default #general channel for a task."""
    ts = now()
    await conn.execute(
        "INSERT INTO channels (task_id, name, is_default, created_by, created_at)"
        " VALUES (%s, %s, TRUE, %s, %s)"
        " ON CONFLICT DO NOTHING",
        (task_id, DEFAULT_CHANNEL, agent_id, ts),
    )


async def _ensure_workspace_channel(workspace_id: int, name: str, conn) -> dict:
    """Idempotently create the channel for a workspace and return it."""
    ts = now()
    await conn.execute(
        "INSERT INTO channels (workspace_id, name, is_default, created_at)"
        " VALUES (%s, %s, TRUE, %s)"
        " ON CONFLICT DO NOTHING",
        (workspace_id, name, ts),
    )
    row = await (await conn.execute(
        "SELECT * FROM channels WHERE workspace_id = %s", (workspace_id,)
    )).fetchone()
    return dict(row)


async def _resolve_workspace_channel(workspace_id: int, conn) -> dict:
    """Get the channel for a workspace, or 404."""
    row = await (await conn.execute(
        "SELECT * FROM channels WHERE workspace_id = %s", (workspace_id,)
    )).fetchone()
    if not row:
        raise HTTPException(404, "workspace channel not found")
    return dict(row)


_TS_LAST = [0.0]


def _generate_ts() -> str:
    """Monotonic per-process microsecond-precision timestamp string."""
    t = time.time()
    if t <= _TS_LAST[0]:
        t = _TS_LAST[0] + 0.000001
    _TS_LAST[0] = t
    return f"{t:.6f}"


def _author_block(row: dict) -> dict:
    """Build the author block for a message row.

    Expects either:
      - row['agent_id'] set (agent author)
      - row['user_id'] set + optional row['user_handle'] / row['user_avatar_url']
        (user author from JOIN with users)
    """
    if row.get("agent_id"):
        agent_id = row["agent_id"]
        return {
            "kind": "agent",
            "id": agent_id,
            "display": agent_id,
            "handle": None,
            "avatar_url": None,
        }
    user_id = row.get("user_id")
    handle = row.get("user_handle") or f"user{user_id}"
    return {
        "kind": "user",
        "id": user_id,
        "display": handle,
        "handle": handle,
        "avatar_url": row.get("user_avatar_url"),
    }


def _message_response(row: dict, reply_count: int = 0, thread_participants: list[dict] | None = None) -> dict:
    return {
        "channel_id": row["channel_id"],
        "ts": row["ts"],
        "agent_id": row.get("agent_id"),
        "user_id": row.get("user_id"),
        "author": _author_block(row),
        "text": row["text"],
        "thread_ts": row["thread_ts"],
        "mentions": list(row.get("mentions") or []),
        "edited_at": row.get("edited_at"),
        "created_at": row["created_at"],
        "reply_count": reply_count,
        "thread_participants": thread_participants or [],
    }


router = APIRouter(prefix="/api/tasks/{owner}/{slug}")


@router.get("/agents")
async def list_task_agents(owner: str, slug: str):
    """Agents who have participated in this task (posted messages or submitted runs)."""
    async with get_db() as conn:
        task_id = await _resolve_task_id(owner, slug, conn)
        rows = await (await conn.execute(
            "SELECT DISTINCT a.id, a.total_runs, a.type, a.harness, a.model, a.avatar_seed,"
            " a.role, a.description, a.last_seen_at, u.handle AS owner_handle"
            " FROM agents a"
            " LEFT JOIN users u ON u.id = a.user_id"
            " WHERE a.id IN ("
            "   SELECT DISTINCT m.agent_id FROM messages m"
            "   JOIN channels c ON c.id = m.channel_id"
            "   WHERE c.task_id = %s AND m.agent_id IS NOT NULL"
            "   UNION"
            "   SELECT DISTINCT r.agent_id FROM runs r"
            "   WHERE r.task_id = %s"
            " )"
            " ORDER BY a.last_seen_at DESC NULLS LAST",
            (task_id, task_id),
        )).fetchall()
    return JSONResponse({"agents": [
        {
            "id": r["id"], "total_runs": r["total_runs"],
            "owner_handle": r["owner_handle"],
            "type": r["type"], "harness": r["harness"], "model": r["model"],
            "avatar_seed": r["avatar_seed"],
            "role": r["role"], "description": r["description"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
        }
        for r in rows
    ]})


@router.post("/channels", status_code=201)
async def create_channel(
    owner: str,
    slug: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
    x_agent_harness: str = Header(""),
    x_agent_model: str = Header(""),
):
    name = (body.get("name") or "").strip()
    _validate_channel_name(name)
    if name == DEFAULT_CHANNEL:
        raise HTTPException(409, f"'{name}' is reserved")
    ts = now()
    async with get_db() as conn:
        kind, _author_id = await _resolve_author(token, x_agent_token, authorization, conn, x_agent_harness, x_agent_model)
        task_id = await _resolve_task_id(owner, slug, conn)
        # created_by FK references agents — set it for agent authors only
        created_by = _author_id if kind == "agent" else None
        await _ensure_default_channels(task_id, created_by, conn)
        existing = await (await conn.execute(
            "SELECT id FROM channels WHERE task_id = %s AND name = %s", (task_id, name)
        )).fetchone()
        if existing:
            raise HTTPException(409, f"channel '{name}' already exists")
        row = await (await conn.execute(
            "INSERT INTO channels (task_id, name, is_default, created_by, created_at)"
            " VALUES (%s, %s, FALSE, %s, %s) RETURNING *",
            (task_id, name, created_by, ts),
        )).fetchone()
    return JSONResponse(_channel_response(dict(row)), status_code=201)


@router.get("/channels")
async def list_channels(owner: str, slug: str):
    async with get_db() as conn:
        task_id = await _resolve_task_id(owner, slug, conn)
        await _ensure_default_channels(task_id, None, conn)
        rows = await (await conn.execute(
            "SELECT * FROM channels WHERE task_id = %s ORDER BY is_default DESC, name ASC",
            (task_id,),
        )).fetchall()
    return JSONResponse({"channels": [_channel_response(dict(r)) for r in rows]})


@router.post("/channels/{name}/messages", status_code=201)
async def post_message(
    owner: str,
    slug: str,
    name: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
    x_agent_harness: str = Header(""),
    x_agent_model: str = Header(""),
):
    text = body.get("text") or ""
    _validate_text(text)
    thread_ts = body.get("thread_ts")
    if thread_ts is not None and not isinstance(thread_ts, str):
        raise HTTPException(400, "thread_ts must be a string")
    ts = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn, x_agent_harness, x_agent_model)
        task_id = await _resolve_task_id(owner, slug, conn)
        await _ensure_default_channels(task_id, author_id if kind == "agent" else None, conn)
        channel = await _resolve_channel(task_id, name, conn)
        if thread_ts is not None:
            parent = await (await conn.execute(
                "SELECT thread_ts FROM messages WHERE channel_id = %s AND ts = %s",
                (channel["id"], thread_ts),
            )).fetchone()
            if not parent:
                raise HTTPException(404, f"parent message '{thread_ts}' not found")
            if parent["thread_ts"] is not None:
                raise HTTPException(400, "cannot reply to a thread reply; reply to the top-level message")
        author_agent = author_id if kind == "agent" else None
        mentions = await mentions_for_message(
            text, conn, channel["id"], thread_ts, kind, author_agent
        )
        agent_col = author_id if kind == "agent" else None
        user_col = author_id if kind == "user" else None
        msg_ts = _generate_ts()
        for _ in range(5):
            try:
                await conn.execute(
                    "INSERT INTO messages (channel_id, ts, agent_id, user_id, text, thread_ts, mentions, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (channel["id"], msg_ts, agent_col, user_col, text, thread_ts, mentions, ts),
                )
                break
            except Exception:
                msg_ts = _generate_ts()
        else:
            raise HTTPException(500, "failed to allocate message ts")
        # Re-fetch with user handle joined for the response
        row = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], msg_ts),
        )).fetchone()
    return JSONResponse(_message_response(dict(row)), status_code=201)


@router.patch("/channels/{name}/messages/{ts}")
async def edit_message(
    owner: str,
    slug: str,
    name: str,
    ts: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
    x_agent_harness: str = Header(""),
    x_agent_model: str = Header(""),
):
    """Edit a message's text. Only the original author can edit."""
    new_text = body.get("text") or ""
    _validate_text(new_text)
    edited_at = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn, x_agent_harness, x_agent_model)
        task_id = await _resolve_task_id(owner, slug, conn)
        channel = await _resolve_channel(task_id, name, conn)
        existing = await (await conn.execute(
            "SELECT * FROM messages WHERE channel_id = %s AND ts = %s",
            (channel["id"], ts),
        )).fetchone()
        if not existing:
            raise HTTPException(404, f"message '{ts}' not found")
        # Only the original author can edit
        if kind == "agent":
            if existing["agent_id"] != author_id:
                raise HTTPException(403, "only the original author can edit this message")
        else:
            if existing["user_id"] != author_id:
                raise HTTPException(403, "only the original author can edit this message")
        tt = existing.get("thread_ts")
        author_agent = author_id if kind == "agent" else None
        mentions = await mentions_for_message(
            new_text,
            conn,
            channel["id"],
            tt,
            kind,
            author_agent,
            exclude_message_ts=ts if tt else None,
        )
        await conn.execute(
            "UPDATE messages SET text = %s, mentions = %s, edited_at = %s"
            " WHERE channel_id = %s AND ts = %s",
            (new_text, mentions, edited_at, channel["id"], ts),
        )
        row = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], ts),
        )).fetchone()
    return JSONResponse(_message_response(dict(row)))


@router.get("/channels/{name}/messages")
async def list_messages(
    owner: str,
    slug: str,
    name: str,
    before: str | None = Query(None),
    limit: int = Query(50),
):
    limit = max(1, min(200, limit))
    async with get_db() as conn:
        task_id = await _resolve_task_id(owner, slug, conn)
        await _ensure_default_channels(task_id, None, conn)
        channel = await _resolve_channel(task_id, name, conn)
        params: list = [channel["id"]]
        where = "m.channel_id = %s AND m.thread_ts IS NULL"
        if before is not None:
            where += " AND m.ts < %s"
            params.append(before)
        params.append(limit)
        rows = await (await conn.execute(
            f"SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            f" LEFT JOIN users u ON u.id = m.user_id"
            f" WHERE {where} ORDER BY m.ts DESC LIMIT %s",
            params,
        )).fetchall()
        rows = list(reversed(rows))
        reply_counts: dict[str, int] = {}
        participants: dict[str, list[dict]] = {}
        if rows:
            ts_values = tuple(r["ts"] for r in rows)
            placeholders = ",".join(["%s"] * len(ts_values))
            reply_rows = await (await conn.execute(
                f"SELECT m.thread_ts, m.agent_id, u.handle AS user_handle,"
                f" u.avatar_url AS user_avatar_url, m.ts FROM messages m"
                f" LEFT JOIN users u ON u.id = m.user_id"
                f" WHERE m.channel_id = %s AND m.thread_ts IN ({placeholders})"
                f" ORDER BY m.ts ASC",
                [channel["id"], *ts_values],
            )).fetchall()
            for r in reply_rows:
                tts = r["thread_ts"]
                reply_counts[tts] = reply_counts.get(tts, 0) + 1
                if r["agent_id"]:
                    entry = {"kind": "agent", "name": r["agent_id"], "avatar_url": None}
                elif r["user_handle"]:
                    entry = {
                        "kind": "user",
                        "name": r["user_handle"],
                        "avatar_url": r["user_avatar_url"],
                    }
                else:
                    continue
                plist = participants.setdefault(tts, [])
                if not any(p["name"] == entry["name"] and p["kind"] == entry["kind"] for p in plist):
                    plist.append(entry)
    messages = [
        _message_response(dict(r), reply_counts.get(r["ts"], 0), participants.get(r["ts"], []))
        for r in rows
    ]
    return JSONResponse({
        "channel": _channel_response(channel),
        "messages": messages,
        "has_more": len(rows) == limit,
    })


@router.get("/channels/{name}/messages/{ts}/replies")
async def list_replies(owner: str, slug: str, name: str, ts: str):
    async with get_db() as conn:
        task_id = await _resolve_task_id(owner, slug, conn)
        await _ensure_default_channels(task_id, None, conn)
        channel = await _resolve_channel(task_id, name, conn)
        parent = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], ts),
        )).fetchone()
        if not parent:
            raise HTTPException(404, f"message '{ts}' not found")
        if parent["thread_ts"] is not None:
            raise HTTPException(400, "not a thread parent")
        replies = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.thread_ts = %s ORDER BY m.ts ASC",
            (channel["id"], ts),
        )).fetchall()
    return JSONResponse({
        "channel": _channel_response(channel),
        "parent": _message_response(dict(parent), len(replies)),
        "replies": [_message_response(dict(r)) for r in replies],
    })


# ──────────────────────────────────────────────────────────────────────────────
# Workspace-scoped messaging (Slack1)
# Each workspace has exactly one channel. Endpoints mirror the task-scoped ones
# but resolve the channel from workspace_id instead of (owner, slug, name).
# ──────────────────────────────────────────────────────────────────────────────

async def _dispatch_workspace_mentions(
    workspace_id: int, mentions: list[str], text: str, msg_ts: str,
    author_kind: str, author_id: str | int,
) -> None:
    """Forward @-mentions to agents with active sessions in this workspace.

    Runs as a background task — failures are logged, not raised.
    """
    if not mentions:
        return
    try:
        from .agent_sdk_client import get_client
        client = get_client()
    except Exception:
        return

    # Determine the author display name
    author_name = str(author_id)

    async with get_db() as conn:
        # Find mentioned agents in this workspace that have active sessions
        placeholders = ",".join(["%s"] * len(mentions))
        rows = await (await conn.execute(
            f"SELECT id, sandbox_id, role, description FROM agents"
            f" WHERE id IN ({placeholders}) AND workspace_id = %s AND sandbox_id IS NOT NULL",
            [*mentions, workspace_id],
        )).fetchall()

    for agent in rows:
        if str(agent["id"]) == str(author_id):
            continue  # don't forward to self
        try:
            # Build the forwarded prompt with agent identity context
            parts = []
            if agent["role"]:
                parts.append(f"Your role: {agent['role']}")
            if agent["description"]:
                parts.append(f"About you: {agent['description']}")
            parts.append(f"You were mentioned in workspace Slack (workspace_id={workspace_id}).")
            parts.append(f"Message from @{author_name}: {text}")
            parts.append(f"Thread ts: {msg_ts}")
            parts.append("")
            parts.append("Reply in the Slack thread using:")
            parts.append(f"  hive chat send --workspace {workspace_id} --thread {msg_ts} '<your reply>'")
            parts.append("")
            parts.append("Do your work, then reply again with results using the same command.")
            prompt = "\n".join(parts)

            # Find the session for this agent's sandbox
            # Look up sessions by agent name pattern
            sessions = await client.list_sessions()
            agent_session = None
            for s in sessions:
                if s.get("agent_id") == agent["id"] or s.get("name") == f"agent-{agent['id']}":
                    agent_session = s
                    break
            if agent_session:
                await client.send_message(agent_session["id"], prompt)
                log.info("Dispatched mention to agent %s (session %s)", agent["id"], agent_session["id"])
        except Exception as e:
            log.warning("Failed to dispatch mention to agent %s: %s", agent["id"], e)


workspace_router = APIRouter(prefix="/api/workspaces/{workspace_id}")


async def _require_workspace_access(workspace_id: int, authorization: str, conn) -> int:
    """Verify the user owns this workspace. Returns user_id."""
    from .main import _get_user_id_from_auth
    user_id = await _get_user_id_from_auth(authorization)
    if user_id is None:
        raise HTTPException(401, "authentication required")
    row = await (await conn.execute(
        "SELECT id FROM workspaces WHERE id = %s AND user_id = %s",
        (workspace_id, user_id),
    )).fetchone()
    if not row:
        raise HTTPException(404, "workspace not found")
    return user_id


@workspace_router.get("/agents")
async def list_workspace_agents(
    workspace_id: int,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    """List agents in this workspace with their roles and descriptions."""
    async with get_db() as conn:
        # Auth: accept either agent token or user auth
        await _resolve_author(token, x_agent_token, authorization, conn)
        rows = await (await conn.execute(
            "SELECT id, type, harness, model, role, description, avatar_seed, last_seen_at"
            " FROM agents WHERE workspace_id = %s ORDER BY registered_at ASC",
            (workspace_id,),
        )).fetchall()
    return JSONResponse({"agents": [
        {
            "id": r["id"], "type": r["type"], "harness": r["harness"], "model": r["model"],
            "role": r["role"], "description": r["description"],
            "avatar_seed": r["avatar_seed"],
            "last_seen_at": r["last_seen_at"].isoformat() if r["last_seen_at"] else None,
        }
        for r in rows
    ]})


@workspace_router.post("/messages", status_code=201)
async def post_workspace_message(
    workspace_id: int,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
    x_agent_harness: str = Header(""),
    x_agent_model: str = Header(""),
):
    text = body.get("text") or ""
    _validate_text(text)
    thread_ts = body.get("thread_ts")
    if thread_ts is not None and not isinstance(thread_ts, str):
        raise HTTPException(400, "thread_ts must be a string")
    ts = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn, x_agent_harness, x_agent_model)
        channel = await _resolve_workspace_channel(workspace_id, conn)
        if thread_ts is not None:
            parent = await (await conn.execute(
                "SELECT thread_ts FROM messages WHERE channel_id = %s AND ts = %s",
                (channel["id"], thread_ts),
            )).fetchone()
            if not parent:
                raise HTTPException(404, f"parent message '{thread_ts}' not found")
            if parent["thread_ts"] is not None:
                raise HTTPException(400, "cannot reply to a thread reply; reply to the top-level message")
        author_agent = author_id if kind == "agent" else None
        mentions = await mentions_for_message(
            text, conn, channel["id"], thread_ts, kind, author_agent,
            workspace_id=workspace_id,
        )
        agent_col = author_id if kind == "agent" else None
        user_col = author_id if kind == "user" else None
        msg_ts = _generate_ts()
        for _ in range(5):
            try:
                await conn.execute(
                    "INSERT INTO messages (channel_id, ts, agent_id, user_id, text, thread_ts, mentions, created_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (channel["id"], msg_ts, agent_col, user_col, text, thread_ts, mentions, ts),
                )
                break
            except Exception:
                msg_ts = _generate_ts()
        else:
            raise HTTPException(500, "failed to allocate message ts")
        row = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], msg_ts),
        )).fetchone()
    # Dispatch mentions to agents in background
    thread_for_reply = thread_ts or msg_ts
    if mentions:
        asyncio.create_task(_dispatch_workspace_mentions(
            workspace_id, mentions, text, thread_for_reply, kind, author_id,
        ))
    return JSONResponse(_message_response(dict(row)), status_code=201)


@workspace_router.get("/messages")
async def list_workspace_messages(
    workspace_id: int,
    before: str | None = Query(None),
    limit: int = Query(50),
):
    limit = max(1, min(200, limit))
    async with get_db() as conn:
        channel = await _resolve_workspace_channel(workspace_id, conn)
        params: list = [channel["id"]]
        where = "m.channel_id = %s AND m.thread_ts IS NULL"
        if before is not None:
            where += " AND m.ts < %s"
            params.append(before)
        params.append(limit)
        rows = await (await conn.execute(
            f"SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            f" LEFT JOIN users u ON u.id = m.user_id"
            f" WHERE {where} ORDER BY m.ts DESC LIMIT %s",
            params,
        )).fetchall()
        rows = list(reversed(rows))
        reply_counts: dict[str, int] = {}
        participants: dict[str, list[dict]] = {}
        if rows:
            ts_values = tuple(r["ts"] for r in rows)
            placeholders = ",".join(["%s"] * len(ts_values))
            reply_rows = await (await conn.execute(
                f"SELECT m.thread_ts, m.agent_id, u.handle AS user_handle,"
                f" u.avatar_url AS user_avatar_url, m.ts FROM messages m"
                f" LEFT JOIN users u ON u.id = m.user_id"
                f" WHERE m.channel_id = %s AND m.thread_ts IN ({placeholders})"
                f" ORDER BY m.ts ASC",
                [channel["id"], *ts_values],
            )).fetchall()
            for r in reply_rows:
                tts = r["thread_ts"]
                reply_counts[tts] = reply_counts.get(tts, 0) + 1
                if r["agent_id"]:
                    entry = {"kind": "agent", "name": r["agent_id"], "avatar_url": None}
                elif r["user_handle"]:
                    entry = {
                        "kind": "user",
                        "name": r["user_handle"],
                        "avatar_url": r["user_avatar_url"],
                    }
                else:
                    continue
                plist = participants.setdefault(tts, [])
                if not any(p["name"] == entry["name"] and p["kind"] == entry["kind"] for p in plist):
                    plist.append(entry)
    messages = [
        _message_response(dict(r), reply_counts.get(r["ts"], 0), participants.get(r["ts"], []))
        for r in rows
    ]
    return JSONResponse({
        "channel": _channel_response(channel),
        "messages": messages,
        "has_more": len(rows) == limit,
    })


@workspace_router.patch("/messages/{ts}")
async def edit_workspace_message(
    workspace_id: int,
    ts: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
    x_agent_harness: str = Header(""),
    x_agent_model: str = Header(""),
):
    new_text = body.get("text") or ""
    _validate_text(new_text)
    edited_at = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn, x_agent_harness, x_agent_model)
        channel = await _resolve_workspace_channel(workspace_id, conn)
        existing = await (await conn.execute(
            "SELECT * FROM messages WHERE channel_id = %s AND ts = %s",
            (channel["id"], ts),
        )).fetchone()
        if not existing:
            raise HTTPException(404, f"message '{ts}' not found")
        if kind == "agent":
            if existing["agent_id"] != author_id:
                raise HTTPException(403, "only the original author can edit this message")
        else:
            if existing["user_id"] != author_id:
                raise HTTPException(403, "only the original author can edit this message")
        tt = existing.get("thread_ts")
        author_agent = author_id if kind == "agent" else None
        mentions = await mentions_for_message(
            new_text, conn, channel["id"], tt, kind, author_agent,
            exclude_message_ts=ts if tt else None,
            workspace_id=workspace_id,
        )
        await conn.execute(
            "UPDATE messages SET text = %s, mentions = %s, edited_at = %s"
            " WHERE channel_id = %s AND ts = %s",
            (new_text, mentions, edited_at, channel["id"], ts),
        )
        row = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], ts),
        )).fetchone()
    return JSONResponse(_message_response(dict(row)))


@workspace_router.get("/messages/{ts}/replies")
async def list_workspace_replies(workspace_id: int, ts: str):
    async with get_db() as conn:
        channel = await _resolve_workspace_channel(workspace_id, conn)
        parent = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.ts = %s",
            (channel["id"], ts),
        )).fetchone()
        if not parent:
            raise HTTPException(404, f"message '{ts}' not found")
        if parent["thread_ts"] is not None:
            raise HTTPException(400, "not a thread parent")
        replies = await (await conn.execute(
            "SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url FROM messages m"
            " LEFT JOIN users u ON u.id = m.user_id"
            " WHERE m.channel_id = %s AND m.thread_ts = %s ORDER BY m.ts ASC",
            (channel["id"], ts),
        )).fetchall()
    return JSONResponse({
        "channel": _channel_response(channel),
        "parent": _message_response(dict(parent), len(replies)),
        "replies": [_message_response(dict(r)) for r in replies],
    })
