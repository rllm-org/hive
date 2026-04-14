from typing import Annotated

import typer

from hive.cli.components.chat import print_channel_list
from hive.cli.formatting import ok
from hive.cli.helpers import _api, _json_out, _split_task_ref, _task_ref
from hive.cli.state import JsonFlag, TaskOpt, _set_task, get_task

channel_app = typer.Typer(no_args_is_help=True)


@channel_app.callback()
def channel_callback(task_opt: TaskOpt = None):
    """Channels — create and list chat channels for a task."""
    _set_task(task_opt)


@channel_app.command("list")
def channel_list(
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """List channels for the current task."""
    _set_task(task_opt)
    owner, slug = _split_task_ref(_task_ref(get_task()))
    data = _api("GET", f"/tasks/{owner}/{slug}/channels")
    if as_json:
        _json_out(data)
        return
    print_channel_list(data.get("channels", []))


@channel_app.command("create")
def channel_create(
    name: Annotated[str, typer.Argument(help="Channel name")],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Create a new channel."""
    _set_task(task_opt)
    owner, slug = _split_task_ref(_task_ref(get_task()))
    data = _api("POST", f"/tasks/{owner}/{slug}/channels", json={"name": name})
    if as_json:
        _json_out(data)
    else:
        ok(f"Created #{data.get('name')}")
