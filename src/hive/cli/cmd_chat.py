from typing import Annotated, Optional

import typer

from hive.cli.components.chat import print_history, print_thread
from hive.cli.formatting import ok
from hive.cli.helpers import _api, _json_out, _split_task_ref, _task_ref
from hive.cli.state import JsonFlag, TaskOpt, WorkspaceOpt, _set_task, _set_workspace, get_task, get_workspace

chat_app = typer.Typer(no_args_is_help=True)


@chat_app.callback()
def chat_callback(task_opt: TaskOpt = None, workspace_opt: WorkspaceOpt = None):
    """Chat — channels, messages, and threads."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)


@chat_app.command("send")
def chat_send(
    text: Annotated[str, typer.Argument(help="Message text")],
    channel: Annotated[str, typer.Option("--channel", "-c", help="Channel name (task mode)")] = "general",
    thread: Annotated[Optional[str], typer.Option("--thread", "-t", help="Reply to a message ts")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
    workspace_opt: WorkspaceOpt = None,
):
    """Post a message to a channel or reply in a thread."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)
    payload: dict = {"text": text}
    if thread:
        payload["thread_ts"] = thread
    ws = get_workspace()
    if ws is not None:
        data = _api("POST", f"/workspaces/{ws}/messages", json=payload)
    else:
        owner, slug = _split_task_ref(_task_ref(get_task()))
        data = _api("POST", f"/tasks/{owner}/{slug}/channels/{channel}/messages", json=payload)
    if as_json:
        _json_out(data)
    else:
        label = f"workspace:{ws}" if ws is not None else f"#{channel}"
        ok(f"{label}  ts={data.get('ts')}")


@chat_app.command("history")
def chat_history(
    channel: Annotated[str, typer.Option("--channel", "-c", help="Channel name (task mode)")] = "general",
    limit: Annotated[int, typer.Option("--limit", "-n", help="Max messages")] = 50,
    before: Annotated[Optional[str], typer.Option("--before", help="Cursor: ts to page back from")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
    workspace_opt: WorkspaceOpt = None,
):
    """Read recent messages in a channel."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)
    params: dict = {"limit": limit}
    if before:
        params["before"] = before
    ws = get_workspace()
    if ws is not None:
        data = _api("GET", f"/workspaces/{ws}/messages", params=params)
    else:
        owner, slug = _split_task_ref(_task_ref(get_task()))
        data = _api("GET", f"/tasks/{owner}/{slug}/channels/{channel}/messages", params=params)
    if as_json:
        _json_out(data)
        return
    label = f"workspace:{ws}" if ws is not None else channel
    print_history(label, data.get("messages", []))


@chat_app.command("thread")
def chat_thread(
    ts: Annotated[str, typer.Argument(help="Parent message ts")],
    channel: Annotated[str, typer.Option("--channel", "-c", help="Channel name (task mode)")] = "general",
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
    workspace_opt: WorkspaceOpt = None,
):
    """Show a thread (parent message and replies)."""
    _set_task(task_opt)
    _set_workspace(workspace_opt)
    ws = get_workspace()
    if ws is not None:
        data = _api("GET", f"/workspaces/{ws}/messages/{ts}/replies")
    else:
        owner, slug = _split_task_ref(_task_ref(get_task()))
        data = _api("GET", f"/tasks/{owner}/{slug}/channels/{channel}/messages/{ts}/replies")
    if as_json:
        _json_out(data)
        return
    label = f"workspace:{ws}" if ws is not None else channel
    print_thread(label, data.get("parent", {}), data.get("replies", []))
