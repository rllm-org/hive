import json
import os
import subprocess
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from hive.cli.formatting import ok, empty
from hive.cli.helpers import _api, _config, _task_ref, _split_task_ref, _json_out, _agent_id
from hive.cli.components import print_task_table, print_clone_instructions, print_context
from hive.cli.console import get_console
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

task_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


def _admin_headers(admin_key: str = "") -> dict[str, str]:
    """Return admin headers for CLI calls that hit admin-only endpoints.
    Prefers the explicit `admin_key` arg, falls back to env/config."""

    admin_key = admin_key or os.environ.get("HIVE_ADMIN_KEY") or _config().get("admin_key") or os.environ.get("ADMIN_KEY")
    return {"X-Admin-Key": admin_key} if admin_key else {}


@task_app.callback()
def task_callback(task_opt: TaskOpt = None):
    """Task management commands.

    A task repo must contain program.md (instructions) and eval/eval.sh
    (evaluation script). Optional: prepare.sh, requirements.txt.
    """
    _set_task(task_opt)


@task_app.command("list")
def task_list(
    public: Annotated[bool, typer.Option("--public", help="Show only public tasks")] = False,
    private: Annotated[bool, typer.Option("--private", help="Show only private tasks")] = False,
    as_json: JsonFlag = False,
):
    """List all tasks."""
    params = {}
    if public:
        params["type"] = "public"
    elif private:
        params["type"] = "private"
    data = _api("GET", "/tasks", params=params)
    tasks = data.get("tasks", [])
    if as_json:
        _json_out(tasks)
        return
    if not tasks:
        empty("No tasks found.")
        return
    print_task_table(tasks)


@task_app.command("create")
def task_create(
    slug: Annotated[str, typer.Argument()],
    name: Annotated[str, typer.Option(help="Human-readable task name")],
    folder: Annotated[str, typer.Option("--path", help="Local folder to upload",
                                        click_type=click.Path(exists=True))],
    description: Annotated[str, typer.Option(help="Task description")],
    admin_key: Annotated[str, typer.Option("--admin-key", envvar="HIVE_ADMIN_KEY", help="Admin key")] = "",
    as_json: JsonFlag = False,
):
    """Create a new task by uploading a local folder to GitHub."""
    import io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(folder, arcname=".")
    buf.seek(0)
    data = _api("POST", "/tasks",
                data={"slug": slug, "name": name, "description": description},
                files={"archive": ("task.tar.gz", buf, "application/gzip")},
                headers=_admin_headers(admin_key))
    if as_json:
        _json_out(data)
    else:
        ok(f"Task created: {data.get('owner', '')}/{data.get('slug', slug)} \u2192 {data['repo_url']}")


@task_app.command("clone")
def task_clone(task_ref: Annotated[str, typer.Argument(help="OWNER/SLUG")]):
    """Clone a task repo. Creates your copy with a deploy key for push access."""
    console = get_console()
    # Legacy compat: bare slug -> hive/{slug}
    if "/" not in task_ref:
        task_ref = f"hive/{task_ref}"
    owner, slug = _split_task_ref(task_ref)

    with console.status(f"[bold]Requesting clone for [cyan]{task_ref}[/cyan]...", spinner="dots") as status:
        resp = _api("POST", f"/tasks/{owner}/{slug}/clone")
        mode = resp.get("mode", "fork")
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

        status.update(f"[bold]Cloning into [cyan]./{slug}/[/cyan]...")

        # Clone via SSH with deploy key — dir uses slug only
        ssh_cmd = f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=no"
        result = subprocess.run(
            ["git", "clone", ssh_url, slug], capture_output=True, text=True,
            env={**os.environ, "GIT_SSH_COMMAND": ssh_cmd},
        )
        if result.returncode != 0:
            raise click.ClickException(f"git clone failed:\n{result.stderr}")

        status.update(f"[bold]Configuring [cyan]{slug}[/cyan]...")

        # Set per-repo SSH command so git fetch always uses the deploy key
        subprocess.run(["git", "-C", slug, "config", "core.sshCommand", ssh_cmd],
                       capture_output=True, text=True)

        if mode == "branch":
            # Branch mode: checkout the initial branch, no upstream remote needed
            default_branch = resp.get("default_branch", "")
            if default_branch:
                subprocess.run(["git", "-C", slug, "checkout", default_branch],
                               capture_output=True, text=True)
            hive_dir = Path(slug) / ".hive"
            hive_dir.mkdir(exist_ok=True)
            (hive_dir / "task").write_text(task_ref)
            (hive_dir / "fork.json").write_text(json.dumps({
                "mode": "branch",
                "branch_prefix": resp.get("branch_prefix", ""),
                "key_path": str(key_path),
            }, indent=2))
            (hive_dir / "agent").write_text(_agent_id())
        else:
            # Fork mode: add upstream remote
            subprocess.run(["git", "-C", slug, "remote", "add", "upstream", upstream_url],
                           capture_output=True, text=True)
            hive_dir = Path(slug) / ".hive"
            hive_dir.mkdir(exist_ok=True)
            (hive_dir / "task").write_text(task_ref)
            (hive_dir / "fork.json").write_text(json.dumps({
                "mode": "fork",
                "fork_url": resp.get("fork_url", ""), "key_path": str(key_path),
            }, indent=2))
            (hive_dir / "agent").write_text(_agent_id())

    ok(f"Cloned {task_ref} into ./{slug}/")
    try:
        name = _agent_id()
    except Exception:
        name = "<agent_name>"
    if mode == "branch":
        console.print(f"  You're on branch [cyan]{resp.get('default_branch', '')}[/cyan]")
        console.print(f"  Use [bold]hive push[/bold] to push your changes")
    else:
        print_clone_instructions(slug, name)


@task_app.command("context")
def task_context(
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Print all-in-one task context."""
    _set_task(task_opt)
    ref = _task_ref(get_task())
    owner, slug = _split_task_ref(ref)
    data = _api("GET", f"/tasks/{owner}/{slug}/context")
    if as_json:
        _json_out(data)
        return
    print_context(data, ref)
