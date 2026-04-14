import json
import re
import time
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import get_db, now


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            default=lambda o: o.isoformat() if isinstance(o, datetime) else (_ for _ in ()).throw(TypeError),
        ).encode("utf-8")


_CHANNEL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,20}$")
_MENTION_RE = re.compile(r"@([a-z0-9][a-z0-9-]{0,30})", re.IGNORECASE)

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
) -> tuple[str, str | int]:
    """Authenticate the caller as either an agent or a user.

    Returns ('agent', agent_id) or ('user', user_id). Agent token takes
    precedence so the CLI keeps working unchanged.
    """
    # Try agent token first (CLI flow)
    effective = x_agent_token or token
    if effective:
        row = await (await conn.execute(
            "SELECT id FROM agents WHERE token = %s OR id = %s", (effective, effective)
        )).fetchone()
        if row:
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
        " ON CONFLICT (task_id, name) DO NOTHING",
        (task_id, DEFAULT_CHANNEL, agent_id, ts),
    )


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


async def _parse_mentions(text: str, conn) -> list[str]:
    """Extract @<name> tokens from text, validate against agents table.

    Returns a deduplicated list of valid agent IDs (preserving first-seen order).
    Invalid names (typos, not registered) are silently dropped.
    """
    seen: list[str] = []
    seen_set: set[str] = set()
    for match in _MENTION_RE.finditer(text):
        name = match.group(1).lower()
        if name in seen_set:
            continue
        seen_set.add(name)
        seen.append(name)
    if not seen:
        return []
    placeholders = ",".join(["%s"] * len(seen))
    rows = await (await conn.execute(
        f"SELECT id FROM agents WHERE id IN ({placeholders})",
        seen,
    )).fetchall()
    valid = {r["id"] for r in rows}
    return [n for n in seen if n in valid]


router = APIRouter(prefix="/api/tasks/{owner}/{slug}")


@router.post("/channels", status_code=201)
async def create_channel(
    owner: str,
    slug: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    name = (body.get("name") or "").strip()
    _validate_channel_name(name)
    if name == DEFAULT_CHANNEL:
        raise HTTPException(409, f"'{name}' is reserved")
    ts = now()
    async with get_db() as conn:
        kind, _author_id = await _resolve_author(token, x_agent_token, authorization, conn)
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
):
    text = body.get("text") or ""
    _validate_text(text)
    thread_ts = body.get("thread_ts")
    if thread_ts is not None and not isinstance(thread_ts, str):
        raise HTTPException(400, "thread_ts must be a string")
    ts = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
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
        mentions = await _parse_mentions(text, conn)
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
):
    """Edit a message's text. Only the original author can edit."""
    new_text = body.get("text") or ""
    _validate_text(new_text)
    edited_at = now()
    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
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
        mentions = await _parse_mentions(new_text, conn)
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
