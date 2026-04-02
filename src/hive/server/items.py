import re

from fastapi import APIRouter, HTTPException, Query

from .db import get_db, now
from .main import JSONResponse, get_agent

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
