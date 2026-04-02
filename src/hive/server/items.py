import re

from fastapi import APIRouter, HTTPException, Query

from .db import get_db, now, paginate
from .main import JSONResponse, get_agent, _parse_sort

VALID_STATUSES = {"backlog", "todo", "in_progress", "done", "cancelled"}
VALID_PRIORITIES = {"none", "low", "medium", "high", "urgent"}
_LABEL_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

router = APIRouter(prefix="/api/tasks/{task_id}/items")


def _task_prefix(task_id: str) -> str:
    return task_id.split("-")[0].upper()


def _validate_fields(body: dict):
    if "status" in body and body["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"invalid status '{body['status']}'")
    if "priority" in body and body["priority"] not in VALID_PRIORITIES:
        raise HTTPException(400, f"invalid priority '{body['priority']}'")
    if "labels" in body:
        for label in body["labels"]:
            if not _LABEL_RE.match(label):
                raise HTTPException(400, f"invalid label '{label}': only [a-zA-Z0-9_-] allowed")


async def _check_task(task_id: str, conn):
    row = await (await conn.execute("SELECT id FROM tasks WHERE id = %s", (task_id,))).fetchone()
    if not row:
        raise HTTPException(404, "task not found")


async def _get_item(item_id: str, task_id: str, conn):
    row = await (await conn.execute(
        "SELECT * FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL",
        (item_id, task_id),
    )).fetchone()
    if not row:
        raise HTTPException(404, "item not found")
    return row


async def _comment_count(item_id: str, conn) -> int:
    row = await (await conn.execute(
        "SELECT COUNT(*) AS cnt FROM item_comments WHERE item_id = %s AND deleted_at IS NULL",
        (item_id,),
    )).fetchone()
    return row["cnt"]


def _item_response(item: dict, comment_count: int) -> dict:
    return {
        "id": item["id"],
        "task_id": item["task_id"],
        "title": item["title"],
        "description": item["description"],
        "status": item["status"],
        "priority": item["priority"],
        "assignee_id": item["assignee_id"],
        "parent_id": item["parent_id"],
        "labels": item["labels"] if item["labels"] is not None else [],
        "created_by": item["created_by"],
        "comment_count": comment_count,
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }


_UPDATABLE_FIELDS = {"title", "description", "status", "priority", "assignee_id", "parent_id", "labels"}


async def _check_cycle(item_id: str, new_parent_id: str, conn):
    if new_parent_id == item_id:
        raise HTTPException(400, "cycle detected: item cannot be its own parent")
    current = new_parent_id
    depth = 0
    while current is not None and depth < 5:
        if current == item_id:
            raise HTTPException(400, "cycle detected: would create circular parent chain")
        row = await (await conn.execute(
            "SELECT parent_id FROM items WHERE id = %s AND deleted_at IS NULL", (current,)
        )).fetchone()
        current = row["parent_id"] if row else None
        depth += 1
    if depth >= 5:
        raise HTTPException(400, "max depth of 5 exceeded")


@router.post("", status_code=201)
async def create_item(task_id: str, body: dict, token: str = Query(...)):
    if not body.get("title"):
        raise HTTPException(400, "title is required")
    _validate_fields(body)
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        await _check_task(task_id, conn)

        if body.get("assignee_id"):
            row = await (await conn.execute(
                "SELECT id FROM agents WHERE id = %s", (body["assignee_id"],)
            )).fetchone()
            if not row:
                raise HTTPException(404, f"assignee '{body['assignee_id']}' not found")

        if body.get("parent_id"):
            row = await (await conn.execute(
                "SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL",
                (body["parent_id"], task_id),
            )).fetchone()
            if not row:
                raise HTTPException(404, f"parent item '{body['parent_id']}' not found")

        seq_row = await (await conn.execute(
            "UPDATE tasks SET item_seq = item_seq + 1 WHERE id = %s RETURNING item_seq",
            (task_id,),
        )).fetchone()
        seq = seq_row["item_seq"]
        prefix = _task_prefix(task_id)
        item_id = f"{prefix}-{seq}"

        await conn.execute(
            "INSERT INTO items (id, seq, task_id, title, description, status, priority,"
            " assignee_id, parent_id, labels, created_by, created_at, updated_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                item_id, seq, task_id,
                body["title"],
                body.get("description"),
                body.get("status", "backlog"),
                body.get("priority", "none"),
                body.get("assignee_id"),
                body.get("parent_id"),
                body.get("labels", []),
                agent_id,
                ts, ts,
            ),
        )

        item = await (await conn.execute(
            "SELECT * FROM items WHERE id = %s", (item_id,)
        )).fetchone()

    resp = _item_response(dict(item), 0)
    return JSONResponse(resp, status_code=201)


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
        rows = await (await conn.execute(
            f"SELECT i.*,"
            f" (SELECT COUNT(*) FROM item_comments c WHERE c.item_id = i.id AND c.deleted_at IS NULL) AS comment_count"
            f" FROM items i WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
            params,
        )).fetchall()

    has_next = len(rows) > per_page
    items = [_item_response(dict(r), r["comment_count"]) for r in rows[:per_page]]
    return JSONResponse({"items": items, "page": page, "per_page": per_page, "has_next": has_next})


@router.post("/bulk", status_code=201)
async def bulk_create_items(task_id: str, body: dict, token: str = Query(...)):
    items_data = body.get("items", [])
    if len(items_data) == 0 or len(items_data) > 50:
        raise HTTPException(400, "items must contain between 1 and 50 entries")
    for item in items_data:
        if not item.get("title"):
            raise HTTPException(400, "title is required")
        _validate_fields(item)
    ts = now()
    async with get_db() as conn:
        agent_id = await get_agent(token, conn)
        await _check_task(task_id, conn)
        created = []
        for item in items_data:
            if item.get("assignee_id"):
                row = await (await conn.execute(
                    "SELECT id FROM agents WHERE id = %s", (item["assignee_id"],)
                )).fetchone()
                if not row:
                    raise HTTPException(404, f"assignee '{item['assignee_id']}' not found")
            if item.get("parent_id"):
                row = await (await conn.execute(
                    "SELECT id FROM items WHERE id = %s AND task_id = %s AND deleted_at IS NULL",
                    (item["parent_id"], task_id),
                )).fetchone()
                if not row:
                    raise HTTPException(404, f"parent item '{item['parent_id']}' not found")
            seq_row = await (await conn.execute(
                "UPDATE tasks SET item_seq = item_seq + 1 WHERE id = %s RETURNING item_seq",
                (task_id,),
            )).fetchone()
            seq = seq_row["item_seq"]
            prefix = _task_prefix(task_id)
            item_id = f"{prefix}-{seq}"
            await conn.execute(
                "INSERT INTO items (id, seq, task_id, title, description, status, priority,"
                " assignee_id, parent_id, labels, created_by, created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    item_id, seq, task_id,
                    item["title"],
                    item.get("description"),
                    item.get("status", "backlog"),
                    item.get("priority", "none"),
                    item.get("assignee_id"),
                    item.get("parent_id"),
                    item.get("labels", []),
                    agent_id,
                    ts, ts,
                ),
            )
            row = await (await conn.execute(
                "SELECT * FROM items WHERE id = %s", (item_id,)
            )).fetchone()
            created.append(_item_response(dict(row), 0))
    return JSONResponse({"items": created}, status_code=201)


@router.patch("/bulk")
async def bulk_update_items(task_id: str, body: dict, token: str = Query(...)):
    items_data = body.get("items", [])
    if len(items_data) == 0 or len(items_data) > 50:
        raise HTTPException(400, "items must contain between 1 and 50 entries")
    updates_list = []
    for item in items_data:
        if not item.get("id"):
            raise HTTPException(400, "each item must have an id")
        updates = {k: v for k, v in item.items() if k in _UPDATABLE_FIELDS}
        _validate_fields(updates)
        updates_list.append((item["id"], updates))
    ts = now()
    async with get_db() as conn:
        await get_agent(token, conn)
        await _check_task(task_id, conn)
        results = []
        for item_id, updates in updates_list:
            await _get_item(item_id, task_id, conn)
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
            if updates:
                set_clauses = ", ".join(f"{k} = %s" for k in updates)
                values = list(updates.values()) + [ts, item_id, task_id]
                await conn.execute(
                    f"UPDATE items SET {set_clauses}, updated_at = %s WHERE id = %s AND task_id = %s",
                    values,
                )
            item = await _get_item(item_id, task_id, conn)
            count = await _comment_count(item_id, conn)
            results.append(_item_response(dict(item), count))
    return JSONResponse({"items": results})


@router.get("/{item_id}")
async def get_item(task_id: str, item_id: str):
    async with get_db() as conn:
        await _check_task(task_id, conn)
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
        await get_agent(token, conn)
        await _check_task(task_id, conn)
        await _get_item(item_id, task_id, conn)

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
        agent_id = await get_agent(token, conn)
        await _check_task(task_id, conn)
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
        agent_id = await get_agent(token, conn)
        await _check_task(task_id, conn)
        item = await _get_item(item_id, task_id, conn)
        if item["assignee_id"] is not None and item["assignee_id"] != agent_id:
            raise HTTPException(409, "item is already assigned to another agent")
        if item["assignee_id"] != agent_id:
            await conn.execute(
                "UPDATE items SET assignee_id = %s, updated_at = %s WHERE id = %s AND task_id = %s",
                (agent_id, ts, item_id, task_id),
            )
        item = await _get_item(item_id, task_id, conn)
        count = await _comment_count(item_id, conn)
    return JSONResponse(_item_response(dict(item), count))
