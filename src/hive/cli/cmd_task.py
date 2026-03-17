import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import click
import typer

from hive.cli.helpers import _api, _config, _task_id, _json_out
from hive.cli.components import print_task_table, print_clone_instructions, print_context
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

task_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@task_app.callback()
def task_callback(task_opt: TaskOpt = None):
    """Task management commands.

    A task repo must contain program.md (instructions) and eval/eval.sh
    (evaluation script). Optional: prepare.sh, requirements.txt.
    """
    _set_task(task_opt)


@task_app.command("list")
def task_list(as_json: JsonFlag = False):
    """List all tasks."""
    data = _api("GET", "/tasks")
    tasks = data.get("tasks", [])
    if as_json:
        _json_out(tasks)
        return
    if not tasks:
        click.echo("No tasks found.")
        return
    print_task_table(tasks)


@task_app.command("create")
def task_create(
    task_id: Annotated[str, typer.Argument()],
    name: Annotated[str, typer.Option(help="Human-readable task name")],
    folder: Annotated[str, typer.Option("--path", help="Local folder to upload",
                                        click_type=click.Path(exists=True))],
    description: Annotated[str, typer.Option(help="Task description")],
    as_json: JsonFlag = False,
):
    """Create a new task by uploading a local folder to GitHub."""
    import io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(folder, arcname=".")
    buf.seek(0)
    data = _api("POST", "/tasks",
                data={"id": task_id, "name": name, "description": description},
                files={"archive": ("task.tar.gz", buf, "application/gzip")})
    if as_json:
        _json_out(data)
    else:
        click.echo(f"Task created: {data['id']} → {data['repo_url']}")


@task_app.command("clone")
def task_clone(task_id: Annotated[str, typer.Argument()]):
    """Clone a task repo. Creates your copy with a deploy key for push access."""
    resp = _api("POST", f"/tasks/{task_id}/clone")
    ssh_url = resp["ssh_url"]
    upstream_url = resp["upstream_url"]
    private_key = resp.get("private_key", "")

    # Save deploy key
    key_dir = Path.home() / ".hive" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    fork_name = ssh_url.split("/")[-1].replace(".git", "")
    key_path = key_dir / fork_name
    if private_key:
        key_path.write_text(private_key)
        key_path.chmod(0o600)

    # Clone via SSH with deploy key
    ssh_cmd = f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
    result = subprocess.run(
        ["git", "clone", ssh_url, task_id], capture_output=True, text=True,
        env={**os.environ, "GIT_SSH_COMMAND": ssh_cmd},
    )
    if result.returncode != 0:
        raise click.ClickException(f"git clone failed:\n{result.stderr}")

    # Set per-repo SSH command so git push always uses the deploy key
    subprocess.run(["git", "-C", task_id, "config", "core.sshCommand", ssh_cmd],
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", task_id, "remote", "add", "upstream", upstream_url],
                   capture_output=True, text=True)

    hive_dir = Path(task_id) / ".hive"
    hive_dir.mkdir(exist_ok=True)
    (hive_dir / "task").write_text(task_id)
    (hive_dir / "fork.json").write_text(json.dumps({
        "fork_url": resp["fork_url"], "key_path": str(key_path),
    }, indent=2))

    click.echo(f"Cloned {task_id} into ./{task_id}/")
    print_clone_instructions(task_id, _config().get("agent_id", "<agent_name>"))


@task_app.command("context")
def task_context(
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Print all-in-one task context."""
    _set_task(task_opt)
    task_id = _task_id(get_task())
    data = _api("GET", f"/tasks/{task_id}/context")
    if as_json:
        _json_out(data)
        return
    print_context(data, task_id)
