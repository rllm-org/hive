import json
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import get_db, now, paginate


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=lambda o: o.isoformat() if isinstance(o, datetime) else (_ for _ in ()).throw(TypeError)).encode("utf-8")

async def _get_agent(token: str, conn) -> str:
    row = await (await conn.execute("SELECT id FROM agents WHERE token = %s", (token,))).fetchone()
    if not row:
        row = await (await conn.execute("SELECT id FROM agents WHERE id = %s", (token,))).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), row["id"]))
    return row["id"]

def _parse_sort(raw: str, allowed: dict[str, str]) -> str:
    parts = raw.split(":", 1)
    field, direction = parts[0], (parts[1].upper() if len(parts) > 1 else "DESC")
    if direction not in ("ASC", "DESC"):
        direction = "DESC"
    return f"{allowed.get(field, list(allowed.values())[0])} {direction}"

VALID_STATUSES = {"backlog", "in_progress", "review", "archived"}
VALID_PRIORITIES = {"none", "low", "medium", "high", "urgent"}
_LABEL_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
ASSIGN_TTL = timedelta(hours=2)

router = APIRouter(prefix="/api/tasks/{task_id}/items")


def _task_prefix(task_id: str) -> str: return task_id.split("-")[0].upper()


def _validate_status_filter(status: str | None):
    if status is None:
        return
    value = status[1:] if status.startswith("!") else status
    if value not in VALID_STATUSES:
        raise HTTPException(400, "invalid status")

def _reject_null_bytes(s: str, field: str):
    if "\x00" in s:
        raise HTTPException(400, f"{field} must not contain null bytes")

def _validate_fields(body: dict):
    if "title" in body:
        t = body["title"]
        if not isinstance(t, str) or not t.strip():
            raise HTTPException(400, "title is required and cannot be blank")
        _reject_null_bytes(t, "title")
        if len(t) > 500:
            raise HTTPException(400, "title max 500 chars")
    if "description" in body and body["description"] is not None:
        if not isinstance(body["description"], str):
            raise HTTPException(400, "description must be a string")
        _reject_null_bytes(body["description"], "description")
        if len(body["description"]) > 10000:
            raise HTTPException(400, "description max 10000 chars")
    if "status" in body and (not isinstance(body["status"], str) or body["status"] not in VALID_STATUSES):
        raise HTTPException(400, f"invalid status")
    if "priority" in body and (not isinstance(body["priority"], str) or body["priority"] not in VALID_PRIORITIES):
        raise HTTPException(400, f"invalid priority")
    if "parent_id" in body and body["parent_id"] is not None and not isinstance(body["parent_id"], str):
        raise HTTPException(400, "parent_id must be a string")
    if "assignee_id" in body and body["assignee_id"] is not None and not isinstance(body["assignee_id"], str):
        raise HTTPException(400, "assignee_id must be a string")
    if "labels" in body:
        labels = body["labels"]
        if not isinstance(labels, list):
            raise HTTPException(400, "labels must be an array")
        if len(labels) > 20:
            raise HTTPException(400, "max 20 labels")
        for label in labels:
            if not isinstance(label, str):
                raise HTTPException(400, "each label must be a string")
            if len(label) > 50:
                raise HTTPException(400, f"label too long (max 50): {label}")
            if not _LABEL_RE.match(label):
                raise HTTPException(400, f"invalid label '{label}': only [a-zA-Z0-9_-] allowed")

async def _check_task(task_id: str, conn):
    if not await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone():
        raise HTTPException(404, "task not found")


async def _get_item(item_id: str, task_id: str, conn):
    row = await (await conn.execute(
        "SELECT * FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL", (item_id, task_id),
    )).fetchone()
    if not row: raise HTTPException(404, "item not found")
    return row

async def _comment_count(item_id: str, conn) -> int:
    row = await (await conn.execute(
        "SELECT COUNT(*) AS cnt FROM item_comments WHERE item_id = %s AND deleted_at IS NULL", (item_id,),
    )).fetchone()
    return row["cnt"]


_ITEM_KEYS = ["id", "task_id", "title", "description", "status", "priority",
              "assignee_id", "assigned_at", "parent_id", "labels", "created_by", "created_at", "updated_at"]

def _item_response(item: dict, comment_count: int) -> dict:
    r = {k: item[k] for k in _ITEM_KEYS}
    r["labels"] = r["labels"] or []
    r["comment_count"] = comment_count
    r["assignment_expires_at"] = r["assigned_at"] + ASSIGN_TTL if r["assigned_at"] else None
    return r


_UPDATABLE_FIELDS = {"title", "description", "status", "priority", "assignee_id", "parent_id", "labels"}

_INSERT_SQL = ("INSERT INTO items (id, seq, task_id, title, description, status, priority,"
               " assignee_id, assigned_at, parent_id, labels, created_by, created_at, updated_at)"
               " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

async def _validate_refs(body: dict, task_id: str, conn):
    if body.get("assignee_id"):
        if not await (await conn.execute("SELECT id FROM agents WHERE id = %s", (body["assignee_id"],))).fetchone():
            raise HTTPException(404, f"assignee '{body['assignee_id']}' not found")
    if body.get("parent_id"):
        if not await (await conn.execute(
            "SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL", (body["parent_id"], task_id),
        )).fetchone():
            raise HTTPException(404, f"parent item '{body['parent_id']}' not found")
        await _check_parent_depth(body["parent_id"], conn)

def _apply_assignment_rules(body: dict, ts, existing: dict | None = None) -> dict:
    updated = dict(body)
    if updated.get("status") == "archived":
        updated["assignee_id"] = None
        updated["assigned_at"] = None
        return updated
    if "assignee_id" not in updated:
        return updated
    if updated["assignee_id"] is None:
        updated["assigned_at"] = None
        return updated
    if existing and existing.get("assignee_id") == updated["assignee_id"] and existing.get("assigned_at") is not None:
        updated["assigned_at"] = existing["assigned_at"]
        return updated
    updated["assigned_at"] = ts
    return updated


async def _insert_item(body: dict, task_id: str, agent_id: str, ts, conn) -> dict:
    seq_row = await (await conn.execute(
        "UPDATE tasks SET item_seq = item_seq + 1 WHERE id = %s RETURNING item_seq", (task_id,),
    )).fetchone()
    seq = seq_row["item_seq"]
    item_id = f"{_task_prefix(task_id)}-{seq}"
    await conn.execute(_INSERT_SQL, (
        item_id, seq, task_id, body["title"], body.get("description"),
        body.get("status", "backlog"), body.get("priority", "none"),
        body.get("assignee_id"), body.get("assigned_at"), body.get("parent_id"), body.get("labels", []),
        agent_id, ts, ts,
    ))
    return dict(await (await conn.execute("SELECT * FROM items WHERE id = %s", (item_id,))).fetchone())


_PARENT_Q = "SELECT parent_id FROM items WHERE id = %s AND deleted_at IS NULL"

async def _depth_above(node_id: str, conn) -> int:
    current, depth = node_id, 0
    while current is not None:
        row = await (await conn.execute(_PARENT_Q, (current,))).fetchone()
        current = row["parent_id"] if row else None
        if current is not None: depth += 1
    return depth

async def _depth_below(node_id: str, conn) -> int:
    rows = await (await conn.execute(
        "SELECT id FROM items WHERE parent_id = %s AND deleted_at IS NULL", (node_id,)
    )).fetchall()
    if not rows: return 0
    return 1 + max([await _depth_below(r["id"], conn) for r in rows])

async def _check_cycle(item_id: str, new_parent_id: str, conn):
    if new_parent_id == item_id:
        raise HTTPException(400, "cycle detected: item cannot be its own parent")
    current = new_parent_id
    while current is not None:
        if current == item_id:
            raise HTTPException(400, "cycle detected: would create circular parent chain")
        row = await (await conn.execute(_PARENT_Q, (current,))).fetchone()
        current = row["parent_id"] if row else None
    above = await _depth_above(new_parent_id, conn)
    below = await _depth_below(item_id, conn)
    if above + 1 + below >= 5:
        raise HTTPException(400, "max depth of 5 exceeded")

async def _check_parent_depth(parent_id: str, conn):
    if await _depth_above(parent_id, conn) + 1 >= 5:
        raise HTTPException(400, "max depth of 5 exceeded")


async def _expire_stale_assignments(conn, ts, task_id: str | None = None, item_id: str | None = None):
    where = [
        "deleted_at IS NULL",
        "assignee_id IS NOT NULL",
        "assigned_at IS NOT NULL",
        "assigned_at <= %s",
    ]
    params: list = [ts - ASSIGN_TTL]
    if task_id is not None:
        where.append("task_id = %s")
        params.append(task_id)
    if item_id is not None:
        where.append("id = %s")
        params.append(item_id)
    await conn.execute(
        f"UPDATE items"
        f" SET assignee_id = NULL, assigned_at = NULL, updated_at = %s"
        f" WHERE {' AND '.join(where)}",
        [ts, *params],
    )


@router.post("", status_code=201)
async def create_item(task_id: str, body: dict, token: str = Query(...)):
    if not body.get("title") or not body["title"].strip():
        raise HTTPException(400, "title is required and cannot be blank")
    _validate_fields(body)
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _validate_refs(body, task_id, conn)
        body = _apply_assignment_rules(body, ts)
        item = await _insert_item(body, task_id, agent_id, ts, conn)
    return JSONResponse(_item_response(dict(item), 0), status_code=201)


_SORT_KEYS = {
    "recent": "i.created_at",
    "updated": "i.updated_at",
    "priority": "CASE i.priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END",
}


@router.get("")
async def list_items(
    task_id: str,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    label: str | None = None,
    parent: str | None = None,
    sort: str = "recent",
    page: int = 1,
    per_page: int = 25,
):
    _validate_status_filter(status)
    if sort.split(":")[0] == "priority" and ":" not in sort:
        sort = "priority:asc"
    order = _parse_sort(sort, _SORT_KEYS)
    page, per_page, offset = paginate(page, per_page)

    where = "i.task_id = %s AND i.deleted_at IS NULL"
    params: list = [task_id]

    if status is not None:
        if status.startswith("!"):
            where += " AND i.status != %s"
            params.append(status[1:])
        else:
            where += " AND i.status = %s"
            params.append(status)
    if priority is not None:
        where += " AND i.priority = %s"
        params.append(priority)
    if assignee is not None:
        if assignee == "none":
            where += " AND i.assignee_id IS NULL"
        else:
            where += " AND i.assignee_id = %s"
            params.append(assignee)
    if label is not None:
        where += " AND i.labels @> %s::text[]"
        params.append([label])
    if parent is not None:
        where += " AND i.parent_id = %s"
        params.append(parent)

    params.extend([per_page + 1, offset])

    async with get_db() as conn:
        await _check_task(task_id, conn)
        await _expire_stale_assignments(conn, now(), task_id=task_id)
        rows = await (await conn.execute(
            f"SELECT i.*,"
            f" (SELECT COUNT(*) FROM item_comments c WHERE c.item_id = i.id AND c.deleted_at IS NULL) AS comment_count"
            f" FROM items i WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
            params,
        )).fetchall()

    has_next = len(rows) > per_page
    items = [_item_response(dict(r), r["comment_count"]) for r in rows[:per_page]]
    return JSONResponse({"items": items, "page": page, "per_page": per_page, "has_next": has_next})


@router.get("/{item_id}")
async def get_item(task_id: str, item_id: str):
    async with get_db() as conn:
        await _check_task(task_id, conn)
        await _expire_stale_assignments(conn, now(), task_id=task_id, item_id=item_id)
        item = await _get_item(item_id, task_id, conn)
        count = await _comment_count(item_id, conn)
        children_rows = await (await conn.execute(
            "SELECT id, title, status FROM items"
            " WHERE parent_id = %s AND task_id = %s AND deleted_at IS NULL"
            " ORDER BY seq ASC",
            (item_id, task_id),
        )).fetchall()

    resp = _item_response(dict(item), count)
    resp["children"] = [{"id": r["id"], "title": r["title"], "status": r["status"]} for r in children_rows]
    return JSONResponse(resp)


@router.patch("/{item_id}")
async def patch_item(task_id: str, item_id: str, body: dict, token: str = Query(...)):
    updates = {k: v for k, v in body.items() if k in _UPDATABLE_FIELDS}
    if not updates:
        raise HTTPException(400, "no updatable fields provided")
    _validate_fields(updates)
    ts = now()
    async with get_db() as conn:
        await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _expire_stale_assignments(conn, ts, task_id=task_id, item_id=item_id)
        item = await _get_item(item_id, task_id, conn)

        if "parent_id" in updates and updates["parent_id"] is not None:
            row = await (await conn.execute(
                "SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL",
                (updates["parent_id"], task_id),
            )).fetchone()
            if not row:
                raise HTTPException(404, f"parent item '{updates['parent_id']}' not found")
            await _check_cycle(item_id, updates["parent_id"], conn)

        if "assignee_id" in updates and updates["assignee_id"] is not None:
            row = await (await conn.execute(
                "SELECT id FROM agents WHERE id = %s", (updates["assignee_id"],)
            )).fetchone()
            if not row:
                raise HTTPException(404, f"assignee '{updates['assignee_id']}' not found")

        updates = _apply_assignment_rules(updates, ts, existing=dict(item))
        set_clauses = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [ts, item_id, task_id]
        await conn.execute(
            f"UPDATE items SET {set_clauses}, updated_at = %s WHERE id = %s AND task_id = %s",
            values,
        )

        item = await _get_item(item_id, task_id, conn)
        count = await _comment_count(item_id, conn)

    return JSONResponse(_item_response(dict(item), count))


@router.delete("/{item_id}", status_code=204)
async def delete_item(task_id: str, item_id: str, token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _expire_stale_assignments(conn, ts, task_id=task_id, item_id=item_id)
        item = await _get_item(item_id, task_id, conn)
        if agent_id != item["created_by"]:
            raise HTTPException(403, "only the creator can delete this item")
        row = await (await conn.execute(
            "SELECT id FROM items WHERE parent_id = %s AND task_id = %s AND deleted_at IS NULL LIMIT 1",
            (item_id, task_id),
        )).fetchone()
        if row:
            raise HTTPException(409, "cannot delete item with children — delete children first")
        await conn.execute("UPDATE items SET deleted_at = %s WHERE id = %s", (ts, item_id))
        await conn.execute(
            "UPDATE item_comments SET deleted_at = %s WHERE item_id = %s AND deleted_at IS NULL",
            (ts, item_id),
        )


@router.post("/{item_id}/assign")
async def assign_item(task_id: str, item_id: str, token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _expire_stale_assignments(conn, ts, task_id=task_id, item_id=item_id)
        item = await _get_item(item_id, task_id, conn)
        if item["status"] == "archived":
            raise HTTPException(409, "archived items cannot be assigned")
        if item["assignee_id"] is not None and item["assignee_id"] != agent_id:
            raise HTTPException(409, "item is already assigned to another agent")
        new_status = "in_progress" if item["status"] == "backlog" else item["status"]
        await conn.execute(
            "UPDATE items SET assignee_id = %s, assigned_at = %s, status = %s, updated_at = %s WHERE id = %s AND task_id = %s",
            (agent_id, ts, new_status, ts, item_id, task_id),
        )
        item = await _get_item(item_id, task_id, conn)
        count = await _comment_count(item_id, conn)
    return JSONResponse(_item_response(dict(item), count))


@router.post("/{item_id}/comments", status_code=201)
async def create_comment(task_id: str, item_id: str, body: dict, token: str = Query(...)):
    content = body.get("content")
    if not content or not isinstance(content, str) or not content.strip():
        raise HTTPException(400, "content is required")
    _reject_null_bytes(content, "content")
    if len(content) > 5000:
        raise HTTPException(400, "content too long")
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _get_item(item_id, task_id, conn)
        row = await (await conn.execute(
            "INSERT INTO item_comments (item_id, agent_id, content, created_at)"
            " VALUES (%s, %s, %s, %s)"
            " RETURNING id, item_id, agent_id, content, created_at",
            (item_id, agent_id, content, ts),
        )).fetchone()
    row = dict(row)
    return JSONResponse(
        {"id": row["id"], "item_id": row["item_id"], "agent_id": row["agent_id"],
         "content": row["content"], "created_at": row["created_at"]},
        status_code=201,
    )


@router.get("/{item_id}/comments")
async def list_comments(task_id: str, item_id: str, page: int = 1, per_page: int = 30):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        await _check_task(task_id, conn)
        await _get_item(item_id, task_id, conn)
        rows = await (await conn.execute(
            "SELECT * FROM item_comments WHERE item_id = %s AND deleted_at IS NULL"
            " ORDER BY created_at ASC LIMIT %s OFFSET %s",
            (item_id, per_page + 1, offset),
        )).fetchall()
    has_next = len(rows) > per_page
    comments = [
        {"id": r["id"], "item_id": r["item_id"], "agent_id": r["agent_id"],
         "content": r["content"], "created_at": r["created_at"]}
        for r in rows[:per_page]
    ]
    return JSONResponse({"comments": comments, "page": page, "per_page": per_page, "has_next": has_next})


@router.delete("/{item_id}/comments/{comment_id}", status_code=204)
async def delete_comment(task_id: str, item_id: str, comment_id: int, token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        await _check_task(task_id, conn)
        await _get_item(item_id, task_id, conn)
        row = await (await conn.execute(
            "SELECT * FROM item_comments WHERE id = %s AND item_id = %s AND deleted_at IS NULL",
            (comment_id, item_id),
        )).fetchone()
        if not row:
            raise HTTPException(404, "comment not found")
        if row["agent_id"] != agent_id:
            raise HTTPException(403, "only the author can delete this comment")
        await conn.execute(
            "UPDATE item_comments SET deleted_at = %s WHERE id = %s",
            (ts, comment_id),
        )


@router.get("/{item_id}/activity")
async def get_item_activity(task_id: str, item_id: str, page: int = 1, per_page: int = 30):
    page, per_page, offset = paginate(page, per_page)
    async with get_db() as conn:
        await _check_task(task_id, conn)
        await _get_item(item_id, task_id, conn)
        rows = await (await conn.execute(
            "SELECT * FROM ("
            "  SELECT 'run' AS type, id::text, agent_id, tldr AS content, score, created_at"
            "  FROM runs WHERE item_id = %s"
            "  UNION ALL"
            "  SELECT 'post' AS type, id::text, agent_id, content, NULL::float AS score, created_at"
            "  FROM posts WHERE item_id = %s"
            "  UNION ALL"
            "  SELECT 'feed_comment' AS type, id::text, agent_id, content, NULL::float AS score, created_at"
            "  FROM comments WHERE item_id = %s"
            "  UNION ALL"
            "  SELECT 'skill' AS type, id::text, agent_id, name AS content, score_delta AS score, created_at"
            "  FROM skills WHERE item_id = %s"
            "  UNION ALL"
            "  SELECT 'item_comment' AS type, id::text, agent_id, content, NULL::float AS score, created_at"
            "  FROM item_comments WHERE item_id = %s AND deleted_at IS NULL"
            ") activity ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (item_id, item_id, item_id, item_id, item_id, per_page + 1, offset),
        )).fetchall()
    has_next = len(rows) > per_page
    entries = [dict(r) for r in rows[:per_page]]
    return JSONResponse({"activity": entries, "page": page, "per_page": per_page, "has_next": has_next})
