import json as json_mod
from typing import Annotated, Optional

import click
import typer

from hive.cli.state import _set_task, set_json_mode
from hive.cli.help_text import HIVE_HELP
from hive.cli.cmd_auth import auth_app
from hive.cli.cmd_task import task_app
from hive.cli.cmd_run import run_app
from hive.cli.cmd_feed import feed_app
from hive.cli.cmd_skill import skill_app
from hive.cli.cmd_search import register_search

app = typer.Typer(
    name="hive",
    rich_markup_mode="rich",
    context_settings={"max_content_width": 120},
    no_args_is_help=False,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    task: Annotated[Optional[str], typer.Option(
        "--task", help="Task ID (overrides .hive/task and HIVE_TASK)"
    )] = None,
):
    """placeholder"""
    set_json_mode(False)
    _set_task(task)
    if ctx.invoked_subcommand is None:
        from hive.cli.banner import print_banner
        print_banner()


app.add_typer(auth_app, name="auth", help="Authentication and identity.")
app.add_typer(task_app, name="task")
app.add_typer(run_app, name="run")
app.add_typer(feed_app, name="feed")
app.add_typer(skill_app, name="skill")
register_search(app)

# Click Group for setuptools entry point and CliRunner compatibility
_base_cli = typer.main.get_command(app)


class HiveGroup(type(_base_cli)):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except click.ClickException as e:
            from hive.cli.state import is_json_mode
            if is_json_mode():
                click.echo(json_mod.dumps({"error": e.format_message()}))
                ctx.exit(e.exit_code)
            else:
                raise


cli = _base_cli
cli.__class__ = HiveGroup

# Set help text from help_text.py (same pattern as upstream)
cli.help = HIVE_HELP
