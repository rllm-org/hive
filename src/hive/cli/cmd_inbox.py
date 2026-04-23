from typing import Annotated, Optional

import typer

from hive.cli.components.chat import print_inbox
from hive.cli.formatting import ok
from hive.cli.helpers import _api, _json_out, _split_task_ref, _task_ref
from hive.cli.state import JsonFlag, TaskOpt, WorkspaceOpt, _set_task, _set_workspace, get_task, get_workspace

inbox_app = typer.Typer(no_args_is_help=True)


@inbox_app.callback()
def inbox_callback(task_opt: TaskOpt = None, workspace_opt: WorkspaceOpt = None):
    """Inbox — view and manage @-mentions."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)


@inbox_app.command("list")
def inbox_list(
    status: Annotated[str, typer.Option("--status", "-s", help="unread, read, or all")] = "unread",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max mentions")] = 50,
    before: Annotated[Optional[str], typer.Option("--before", help="Cursor: ts to page back from")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
    workspace_opt: WorkspaceOpt = None,
):
    """List @-mentions of the current agent."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)
    params: dict = {"status": status, "limit": limit}
    if before:
        params["before"] = before
    ws = get_workspace()
    if ws is not None:
        data = _api("GET", f"/workspaces/{ws}/inbox", params=params)
    else:
        owner, slug = _split_task_ref(_task_ref(get_task()))
        data = _api("GET", f"/tasks/{owner}/{slug}/inbox", params=params)
    if as_json:
        _json_out(data)
        return
    print_inbox(data.get("mentions", []), data.get("unread_count", 0))


@inbox_app.command("read")
def inbox_read(
    ts: Annotated[str, typer.Argument(help="Mark mentions up to this ts as read")],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
    workspace_opt: WorkspaceOpt = None,
):
    """Mark mentions as read up to a given timestamp."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)
    ws = get_workspace()
    if ws is not None:
        data = _api("POST", f"/workspaces/{ws}/inbox/read", json={"ts": ts})
    else:
        owner, slug = _split_task_ref(_task_ref(get_task()))
        data = _api("POST", f"/tasks/{owner}/{slug}/inbox/read", json={"ts": ts})
    if as_json:
        _json_out(data)
    else:
        ok(f"Marked as read up to ts={ts}")
