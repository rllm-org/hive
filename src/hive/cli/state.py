from typing import Annotated, Optional

import typer

_cli_task: str | None = None


def _set_task(task: str | None):
    global _cli_task
    if task:
        _cli_task = task


def get_task() -> str | None:
    return _cli_task


TaskOpt = Annotated[Optional[str], typer.Option("--task", help="Task ID", hidden=True)]
JsonFlag = Annotated[bool, typer.Option("--json", help="Output as JSON")]
