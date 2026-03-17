from typing import Annotated, Optional

import typer

_cli_task: str | None = None
_json_mode: bool = False


def _set_task(task: str | None):
    global _cli_task
    if task:
        _cli_task = task


def get_task() -> str | None:
    return _cli_task


def set_json_mode(enabled: bool) -> None:
    global _json_mode
    _json_mode = enabled


def is_json_mode() -> bool:
    return _json_mode


def _json_callback(value: bool) -> bool:
    if value:
        set_json_mode(True)
    return value


TaskOpt = Annotated[Optional[str], typer.Option("--task", help="Task ID", hidden=True)]
JsonFlag = Annotated[bool, typer.Option("--json", help="Output as JSON", callback=_json_callback, is_eager=True)]
