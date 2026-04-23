import json
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


router = APIRouter(prefix="/api/tasks/{owner}/{slug}")


@router.get("/inbox")
async def list_inbox(
    owner: str,
    slug: str,
    status: str = Query("unread"),
    before: str | None = Query(None),
    limit: int = Query(50),
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    """List messages that @-mention the authenticated agent."""
    if status not in ("unread", "read", "all"):
        raise HTTPException(400, "status must be 'unread', 'read', or 'all'")
    limit = max(1, min(100, limit))

    from .channels import _resolve_author, _resolve_task_id, _message_response

    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
        if kind != "agent":
            raise HTTPException(403, "inbox is agent-only")
        task_id = await _resolve_task_id(owner, slug, conn)

        # Get cursor
        cursor_row = await (await conn.execute(
            "SELECT last_read_ts FROM inbox_cursors WHERE agent_id = %s AND task_id = %s",
            (author_id, task_id),
        )).fetchone()
        last_read_ts = cursor_row["last_read_ts"] if cursor_row else "0"

        # Build query
        params: list = [author_id, task_id]
        where = "%s = ANY(m.mentions) AND c.task_id = %s"

        if status == "unread":
            where += " AND m.ts > %s"
            params.append(last_read_ts)
        elif status == "read":
            where += " AND m.ts <= %s"
            params.append(last_read_ts)

        if before is not None:
            where += " AND m.ts < %s"
            params.append(before)

        params.append(limit)

        rows = await (await conn.execute(
            f"SELECT m.*, c.name AS channel_name,"
            f" u.handle AS user_handle, u.avatar_url AS user_avatar_url"
            f" FROM messages m"
            f" JOIN channels c ON c.id = m.channel_id"
            f" LEFT JOIN users u ON u.id = m.user_id"
            f" WHERE {where}"
            f" ORDER BY m.ts DESC LIMIT %s",
            params,
        )).fetchall()

        # Count total unread
        unread_row = await (await conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages m"
            " JOIN channels c ON c.id = m.channel_id"
            " WHERE %s = ANY(m.mentions) AND c.task_id = %s AND m.ts > %s",
            (author_id, task_id, last_read_ts),
        )).fetchone()
        unread_count = unread_row["cnt"] if unread_row else 0

    mentions = []
    for r in rows:
        row = dict(r)
        msg = _message_response(row)
        msg["channel"] = row["channel_name"]
        mentions.append(msg)

    return JSONResponse({
        "mentions": mentions,
        "unread_count": unread_count,
        "has_more": len(rows) == limit,
    })


@router.post("/inbox/read")
async def mark_read(
    owner: str,
    slug: str,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    """Advance the read cursor. Everything at or before `ts` becomes read."""
    ts = body.get("ts")
    if not ts or not isinstance(ts, str):
        raise HTTPException(400, "ts is required (string)")

    from .channels import _resolve_author, _resolve_task_id

    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
        if kind != "agent":
            raise HTTPException(403, "inbox is agent-only")
        task_id = await _resolve_task_id(owner, slug, conn)

        await conn.execute(
            "INSERT INTO inbox_cursors (agent_id, task_id, last_read_ts, updated_at)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (agent_id, task_id)"
            " DO UPDATE SET last_read_ts = GREATEST(inbox_cursors.last_read_ts, EXCLUDED.last_read_ts),"
            "              updated_at = EXCLUDED.updated_at",
            (author_id, task_id, ts, now()),
        )

    return JSONResponse({"ok": True, "last_read_ts": ts})


# ──────────────────────────────────────────────────────────────────────────────
# Workspace-scoped inbox
# ──────────────────────────────────────────────────────────────────────────────

workspace_inbox_router = APIRouter(prefix="/api/workspaces/{workspace_id}")


@workspace_inbox_router.get("/inbox")
async def list_workspace_inbox(
    workspace_id: int,
    status: str = Query("unread"),
    before: str | None = Query(None),
    limit: int = Query(50),
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    """List messages that @-mention the authenticated agent in this workspace."""
    if status not in ("unread", "read", "all"):
        raise HTTPException(400, "status must be 'unread', 'read', or 'all'")
    limit = max(1, min(100, limit))

    from .channels import _resolve_author, _resolve_workspace_channel, _message_response

    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
        if kind != "agent":
            raise HTTPException(403, "inbox is agent-only")
        channel = await _resolve_workspace_channel(workspace_id, conn)

        # Use workspace_id as cursor scope (reuse inbox_cursors with a synthetic task_id)
        # For workspace inbox, we use negative workspace_id to avoid collision with task_ids
        cursor_key = -workspace_id
        cursor_row = await (await conn.execute(
            "SELECT last_read_ts FROM inbox_cursors WHERE agent_id = %s AND task_id = %s",
            (author_id, cursor_key),
        )).fetchone()
        last_read_ts = cursor_row["last_read_ts"] if cursor_row else "0"

        params: list = [author_id, channel["id"]]
        where = "%s = ANY(m.mentions) AND m.channel_id = %s"

        if status == "unread":
            where += " AND m.ts > %s"
            params.append(last_read_ts)
        elif status == "read":
            where += " AND m.ts <= %s"
            params.append(last_read_ts)

        if before is not None:
            where += " AND m.ts < %s"
            params.append(before)

        params.append(limit)

        rows = await (await conn.execute(
            f"SELECT m.*, u.handle AS user_handle, u.avatar_url AS user_avatar_url"
            f" FROM messages m"
            f" LEFT JOIN users u ON u.id = m.user_id"
            f" WHERE {where}"
            f" ORDER BY m.ts DESC LIMIT %s",
            params,
        )).fetchall()

        unread_row = await (await conn.execute(
            "SELECT COUNT(*) AS cnt FROM messages m"
            " WHERE %s = ANY(m.mentions) AND m.channel_id = %s AND m.ts > %s",
            (author_id, channel["id"], last_read_ts),
        )).fetchone()
        unread_count = unread_row["cnt"] if unread_row else 0

    mentions = [_message_response(dict(r)) for r in rows]

    return JSONResponse({
        "mentions": mentions,
        "unread_count": unread_count,
        "has_more": len(rows) == limit,
    })


@workspace_inbox_router.post("/inbox/read")
async def mark_workspace_read(
    workspace_id: int,
    body: dict,
    token: str = Query(""),
    x_agent_token: str = Header(""),
    authorization: str = Header(""),
):
    """Advance the read cursor for workspace mentions."""
    ts = body.get("ts")
    if not ts or not isinstance(ts, str):
        raise HTTPException(400, "ts is required (string)")

    from .channels import _resolve_author, _resolve_workspace_channel

    async with get_db() as conn:
        kind, author_id = await _resolve_author(token, x_agent_token, authorization, conn)
        if kind != "agent":
            raise HTTPException(403, "inbox is agent-only")
        await _resolve_workspace_channel(workspace_id, conn)

        cursor_key = -workspace_id
        await conn.execute(
            "INSERT INTO inbox_cursors (agent_id, task_id, last_read_ts, updated_at)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (agent_id, task_id)"
            " DO UPDATE SET last_read_ts = GREATEST(inbox_cursors.last_read_ts, EXCLUDED.last_read_ts),"
            "              updated_at = EXCLUDED.updated_at",
            (author_id, cursor_key, ts, now()),
        )

    return JSONResponse({"ok": True, "last_read_ts": ts})
