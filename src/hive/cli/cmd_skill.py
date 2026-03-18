from pathlib import Path
from typing import Annotated

import click
import typer

from hive.cli.formatting import ok, empty
from hive.cli.helpers import _api, _task_id, _json_out
from hive.cli.components import print_skills_list, print_skill_detail
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

skill_app = typer.Typer(no_args_is_help=True)


@skill_app.callback()
def skill_callback(task_opt: TaskOpt = None):
    """Skills library commands."""
    _set_task(task_opt)


@skill_app.command("add")
def skill_add(
    name: Annotated[str, typer.Option(help="Skill name")],
    description: Annotated[str, typer.Option(help="Skill description")],
    filepath: Annotated[Path, typer.Option("--file", exists=True, dir_okay=False)],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Add a skill from a file."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    code = filepath.read_text()
    data = _api("POST", f"/tasks/{task_id}/skills",
                json={"name": name, "description": description, "code_snippet": code})
    if as_json:
        _json_out(data)
    else:
        ok(f"Skill #{data.get('id')} {name!r} added")


@skill_app.command("search")
def skill_search(
    query: Annotated[str, typer.Argument()],
    page: Annotated[int, typer.Option(show_default=True, help="Page number")] = 1,
    per_page: Annotated[int, typer.Option(show_default=True, help="Items per page")] = 20,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Search skills."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("GET", f"/tasks/{task_id}/skills", params={"q": query, "page": page, "per_page": per_page})
    skills = data.get("skills", [])
    if as_json:
        _json_out(skills)
        return
    if not skills:
        empty("No skills found.")
        return
    print_skills_list(skills)
    if data.get("has_next"):
        click.echo(f"  page {page} — more results available (--page {page + 1})")


@skill_app.command("view")
def skill_view(
    id: Annotated[str, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """View a skill by id."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("GET", f"/tasks/{task_id}/skills", params={"q": id})
    skills = data.get("skills", [])
    match = next((s for s in skills if str(s.get("id")) == str(id)), None)
    if not match:
        raise click.ClickException(f"Skill {id!r} not found")
    if as_json:
        _json_out(match)
        return
    print_skill_detail(match)
