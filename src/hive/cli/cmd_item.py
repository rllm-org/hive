from typing import Annotated, Optional

import click
import httpx
import typer

from hive.cli.console import get_console
from hive.cli.formatting import ok, empty, relative_time
from hive.cli.helpers import _api, _task_id, _json_out, _server_url, _active_agent, _agent_id
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

item_app = typer.Typer(no_args_is_help=True)


@item_app.callback()
def item_callback(task_opt: TaskOpt = None):
    """Work items -- create, track, and manage tasks."""
    _set_task(task_opt)


def _list_items_data(
    task_id: str,
    *,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    label: Optional[str] = None,
    parent: Optional[str] = None,
    sort: str = "recent",
    page: int = 1,
    per_page: int = 20,
):
    params = {"sort": sort, "page": page, "per_page": per_page}
    if status is not None:
        params["status"] = status
    if priority is not None:
        params["priority"] = priority
    if assignee is not None:
        params["assignee"] = assignee
    if label is not None:
        params["label"] = label
    if parent is not None:
        params["parent"] = parent
    return _api("GET", f"/tasks/{task_id}/items", params=params)


def _print_items(data, *, page: int):
    items = data.get("items", data) if isinstance(data, dict) else data
    if not items:
        empty("No items.")
        return
    from rich.table import Table
    console = get_console()
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    table.add_column("ID")
    table.add_column("STATUS")
    table.add_column("PRIORITY")
    table.add_column("ASSIGNEE")
    table.add_column("TITLE")
    for item in items:
        table.add_row(
            item.get("slug") or str(item.get("id", "")),
            item.get("status", ""),
            item.get("priority", ""),
            item.get("assignee_id") or "",
            item.get("title", ""),
        )
    console.print(table)
    if isinstance(data, dict) and data.get("has_next"):
        click.echo(f"  page {page} -- more results available (--page {page + 1})")


@item_app.command("create")
def item_create(
    title: Annotated[str, typer.Option("--title", "-t", help="Item title")],
    description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
    status: Annotated[str, typer.Option(help="backlog|in_progress|review|archived")] = "backlog",
    priority: Annotated[str, typer.Option(help="none|urgent|high|medium|low")] = "none",
    label: Annotated[Optional[list[str]], typer.Option("--label", "-l", help="Label (repeatable)")] = None,
    assignee: Annotated[Optional[str], typer.Option(help="Agent ID")] = None,
    parent: Annotated[Optional[str], typer.Option(help="Parent item ID")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Create a new work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    payload = {"title": title, "status": status, "priority": priority}
    if description is not None:
        payload["description"] = description
    if label:
        payload["labels"] = label
    if assignee is not None:
        payload["assignee_id"] = assignee
    if parent is not None:
        payload["parent_id"] = parent
    data = _api("POST", f"/tasks/{task_id}/items", json=payload)
    if as_json:
        _json_out(data)
    else:
        item = data.get("item", data)
        ok(f"Created {item.get('slug', item.get('id'))} \"{item.get('title')}\" ({item.get('status')}, {item.get('priority')})")


@item_app.command("list")
def item_list(
    status: Annotated[Optional[str], typer.Option(help="Filter by status, prefix ! to negate")] = None,
    priority: Annotated[Optional[str], typer.Option()] = None,
    assignee: Annotated[Optional[str], typer.Option(help="Agent ID or 'none'")] = None,
    label: Annotated[Optional[str], typer.Option()] = None,
    parent: Annotated[Optional[str], typer.Option()] = None,
    sort: Annotated[str, typer.Option(help="recent|updated|priority")] = "recent",
    page: Annotated[int, typer.Option()] = 1,
    per_page: Annotated[int, typer.Option()] = 20,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """List work items."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _list_items_data(
        task_id,
        status=status,
        priority=priority,
        assignee=assignee,
        label=label,
        parent=parent,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    if as_json:
        _json_out(data.get("items", data))
        return
    _print_items(data, page=page)


@item_app.command("mine")
def item_mine(
    status: Annotated[Optional[str], typer.Option(help="Filter by status, prefix ! to negate")] = "!archived",
    priority: Annotated[Optional[str], typer.Option()] = None,
    label: Annotated[Optional[str], typer.Option()] = None,
    parent: Annotated[Optional[str], typer.Option()] = None,
    sort: Annotated[str, typer.Option(help="recent|updated|priority")] = "updated",
    page: Annotated[int, typer.Option()] = 1,
    per_page: Annotated[int, typer.Option()] = 20,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """List items assigned to the current agent."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _list_items_data(
        task_id,
        status=status,
        priority=priority,
        assignee=_agent_id(),
        label=label,
        parent=parent,
        sort=sort,
        page=page,
        per_page=per_page,
    )
    if as_json:
        _json_out(data.get("items", data))
        return
    _print_items(data, page=page)


@item_app.command("view")
def item_view(
    item_id: Annotated[str, typer.Argument(help="Item ID (e.g., GSM-1)")],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """View a work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("GET", f"/tasks/{task_id}/items/{item_id}")
    try:
        comments_data = _api("GET", f"/tasks/{task_id}/items/{item_id}/comments", params={"per_page": 100})
        comments = comments_data.get("comments", comments_data) if isinstance(comments_data, dict) else comments_data
    except click.ClickException:
        comments = []
    if as_json:
        _json_out({"item": data, "comments": comments})
        return
    item = data.get("item", data) if isinstance(data, dict) and "item" in data else data
    console = get_console()
    slug = item.get("slug") or str(item.get("id", ""))
    console.print(f"\n=== {slug}: {item.get('title')} ===")
    assignee = item.get("assignee_id") or "unassigned"
    console.print(f"Status: {item.get('status')}  Priority: {item.get('priority')}  Assignee: {assignee}")
    assigned_at = item.get("assigned_at")
    if assigned_at:
        assigned = relative_time(assigned_at)
        expires = relative_time(item.get("assignment_expires_at", "")) if item.get("assignment_expires_at") else ""
        console.print(f"Assigned: {assigned}  Expires: {expires}")
    labels = item.get("labels") or []
    if labels:
        console.print(f"Labels: {', '.join(labels)}")
    creator = item.get("created_by") or ""
    created = relative_time(item.get("created_at", "")) if item.get("created_at") else ""
    updated = relative_time(item.get("updated_at", "")) if item.get("updated_at") else ""
    if creator or created or updated:
        console.print(f"Created by: {creator}  Created: {created}  Updated: {updated}")
    desc = item.get("description") or ""
    if desc:
        console.print(f"\n{desc}")
    subtasks = item.get("subtasks") or item.get("children") or []
    if subtasks:
        console.print("\n=== SUBTASKS ===")
        for sub in subtasks:
            sub_slug = sub.get("slug") or str(sub.get("id", ""))
            console.print(f'  {sub_slug}  {sub.get("status", "")}  "{sub.get("title", "")}"')
    if comments:
        console.print(f"\n=== COMMENTS ({len(comments)}) ===")
        for c in comments:
            ts = relative_time(c.get("created_at", "")) if c.get("created_at") else ""
            author = c.get("agent_id") or c.get("author") or ""
            text = c.get("content") or c.get("text") or ""
            console.print(f'  [{ts}] {author}: "{text}"')


@item_app.command("update")
def item_update(
    item_id: Annotated[str, typer.Argument()],
    title: Annotated[Optional[str], typer.Option("--title", "-t")] = None,
    description: Annotated[Optional[str], typer.Option("--description", "-d")] = None,
    status: Annotated[Optional[str], typer.Option()] = None,
    priority: Annotated[Optional[str], typer.Option()] = None,
    assignee: Annotated[Optional[str], typer.Option(help="Agent ID, or empty to unassign")] = None,
    label: Annotated[Optional[list[str]], typer.Option("--label", "-l")] = None,
    parent: Annotated[Optional[str], typer.Option()] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Update a work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    payload = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if status is not None:
        payload["status"] = status
    if priority is not None:
        payload["priority"] = priority
    if assignee is not None:
        payload["assignee_id"] = assignee if assignee else None
    if label is not None:
        payload["labels"] = label
    if parent is not None:
        payload["parent_id"] = parent
    if not payload:
        raise click.ClickException("No fields to update.")
    data = _api("PATCH", f"/tasks/{task_id}/items/{item_id}", json=payload)
    if as_json:
        _json_out(data)
    else:
        item = data.get("item", data) if isinstance(data, dict) else data
        ok(f"Updated {item.get('slug', item_id)}")


@item_app.command("assign")
def item_assign(
    item_id: Annotated[str, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Assign item to current agent."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("POST", f"/tasks/{task_id}/items/{item_id}/assign")
    if as_json:
        _json_out(data)
    else:
        item = data.get("item", data) if isinstance(data, dict) else data
        ok(f"Assigned {item.get('slug', item_id)} to {item.get('assignee_id', 'you')}")


@item_app.command("delete")
def item_delete(
    item_id: Annotated[str, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Delete a work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    url = _server_url().rstrip("/") + f"/api/tasks/{task_id}/items/{item_id}"
    try:
        agent = _active_agent()
        token = agent.get("token", "")
    except click.ClickException:
        token = ""
    resp = httpx.delete(url, params={"token": token}, headers={"ngrok-skip-browser-warning": "1"}, timeout=30)
    if resp.status_code == 204:
        ok(f"Deleted {item_id}")
    elif resp.status_code == 404:
        raise click.ClickException(f"Item {item_id} not found")
    elif resp.status_code == 409:
        detail = resp.json().get("detail", "conflict")
        raise click.ClickException(detail)
    elif resp.status_code == 403:
        raise click.ClickException("Only the creator can delete this item")
    else:
        raise click.ClickException(f"Server error {resp.status_code}: {resp.text}")


@item_app.command("comment")
def item_comment(
    item_id: Annotated[str, typer.Argument(help="Item ID (e.g., GSM-1)")],
    text: Annotated[str, typer.Argument(help="Comment text")],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Add a comment to a work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("POST", f"/tasks/{task_id}/items/{item_id}/comments", json={"content": text})
    if as_json:
        _json_out(data)
    else:
        comment = data.get("comment", data) if isinstance(data, dict) else data
        ok(f"Comment #{comment.get('id', '')} posted")


@item_app.command("uncomment")
def item_uncomment(
    item_id: Annotated[str, typer.Argument(help="Item ID (e.g., GSM-1)")],
    comment_id: Annotated[int, typer.Argument(help="Comment ID")],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Delete a comment from a work item."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    from hive.cli.helpers import _server_url, _active_agent
    import httpx
    url = _server_url().rstrip("/") + f"/api/tasks/{task_id}/items/{item_id}/comments/{comment_id}"
    try:
        agent = _active_agent()
        token = agent.get("token", "")
    except click.ClickException:
        token = ""
    resp = httpx.delete(url, params={"token": token}, headers={"ngrok-skip-browser-warning": "1"}, timeout=30)
    if resp.status_code == 204:
        ok(f"Deleted comment {comment_id}")
    elif resp.status_code == 404:
        raise click.ClickException(f"Comment {comment_id} not found")
    elif resp.status_code == 403:
        raise click.ClickException("Only the author can delete this comment")
    else:
        raise click.ClickException(f"Server error {resp.status_code}: {resp.text}")
