from typing import Annotated, Optional

import typer

from hive.cli.components.chat import print_inbox
from hive.cli.formatting import ok
from hive.cli.helpers import _api, _json_out, _split_task_ref, _task_ref
from hive.cli.state import JsonFlag, TaskOpt, _set_task, get_task

inbox_app = typer.Typer(no_args_is_help=True)


@inbox_app.callback()
def inbox_callback(task_opt: TaskOpt = None):
    """Inbox — view and manage @-mentions."""
    _set_task(task_opt)


@inbox_app.command("list")
def inbox_list(
    status: Annotated[str, typer.Option("--status", "-s", help="unread, read, or all")] = "unread",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max mentions")] = 50,
    before: Annotated[Optional[str], typer.Option("--before", help="Cursor: ts to page back from")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """List @-mentions of the current agent."""
    _set_task(task_opt)
    owner, slug = _split_task_ref(_task_ref(get_task()))
    params: dict = {"status": status, "limit": limit}
    if before:
        params["before"] = before
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
):
    """Mark mentions as read up to a given timestamp."""
    _set_task(task_opt)
    owner, slug = _split_task_ref(_task_ref(get_task()))
    data = _api("POST", f"/tasks/{owner}/{slug}/inbox/read", json={"ts": ts})
    if as_json:
        _json_out(data)
    else:
        ok(f"Marked as read up to ts={ts}")
