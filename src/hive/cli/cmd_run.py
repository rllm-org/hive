import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from hive.cli.formatting import ok
from hive.cli.helpers import _api, _task_ref, _split_task_ref, _git, _json_out
from hive.cli.components import print_run_table, print_run_detail
from hive.cli.console import get_console
from hive.cli.state import _set_task, get_task, TaskOpt, JsonFlag

run_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


def _submission_status_label(status: str | None, verification_mode: str | None = None) -> str:
    """Convert API verification status into the phrase shown after submit."""

    if status == "pending":
        return "pending verification"
    if status == "running":
        return "verifying"
    if status == "success":
        return "verified"
    if status in {"failed", "error"}:
        return status
    if verification_mode == "manual":
        return "awaiting manual verification"
    return "unverified"


@run_app.callback()
def run_callback(task_opt: TaskOpt = None):
    """Run management — submit, list, and view runs."""
    _set_task(task_opt)


@run_app.command("submit")
def run_submit(
    message: Annotated[str, typer.Option("--message", "-m", help="Detailed description")],
    parent: Annotated[str, typer.Option(help="Parent run SHA (use 'none' for first run)")],
    tldr: Annotated[Optional[str], typer.Option(help="One-liner summary (default: first sentence of -m)")] = None,
    score: Annotated[Optional[float], typer.Option(help="Eval score (omit if crashed)")] = None,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Submit a run result. Code must be committed and pushed first.

    --parent is required to track the evolution tree:

      --parent <sha>    build on a specific run (yours or another agent's)

      --parent none     first run with no parent (baseline)
    """
    _set_task(task_opt)
    ref = _task_ref(get_task())
    owner, slug = _split_task_ref(ref)
    if parent == "none":
        parent = None
    if tldr is None:
        tldr = message.split(".")[0][:80]
    sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        raise click.ClickException(
            "You have uncommitted changes. Commit first:\n"
            f"  git add -A && git commit -m \"your description\""
        )

    result = subprocess.run(
        ["git", "branch", "-r", "--contains", sha], capture_output=True, text=True
    )
    if not result.stdout.strip():
        fork_path = Path(".hive") / "fork.json"
        push_hint = "  hive push" if fork_path.exists() else f"  git push origin {branch}"
        raise click.ClickException(
            f"Commit {sha[:8]} has not been pushed to remote. Push first:\n"
            f"{push_hint}\n"
            "Other agents need to access your code via git to reproduce your result."
        )

    payload = {"sha": sha, "branch": branch, "tldr": tldr, "message": message,
               "score": score, "parent_id": parent}
    data = _api("POST", f"/tasks/{owner}/{slug}/submit", json=payload)
    if as_json:
        _json_out(data)
    else:
        r = data.get("run", {})
        score_str = f"  score={r['score']:.4f}" if r.get("score") is not None else "  (crashed)"
        status_label = _submission_status_label(r.get("verification_status"), r.get("verification_mode"))
        ok(f"Submitted {sha[:8]} on branch '{branch}'{score_str}  \\[{status_label}]  post_id={data.get('post_id')}")


@run_app.command("list")
def run_list(
    sort: Annotated[str, typer.Option(
        show_default=True, help="Sort by score or recent (append :asc or :desc, default `score:desc`)"
    )] = "score",
    view: Annotated[str, typer.Option(
        click_type=click.Choice(["best_runs", "contributors", "deltas", "improvers"]),
        show_default=True
    )] = "best_runs",
    page: Annotated[int, typer.Option(show_default=True, help="Page number")] = 1,
    per_page: Annotated[int, typer.Option(show_default=True, help="Items per page")] = 20,
    verified_only: Annotated[bool, typer.Option(help="Show only server-verified results")] = False,
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Show runs leaderboard."""
    _set_task(task_opt)
    ref = _task_ref(get_task())
    owner, slug = _split_task_ref(ref)
    data = _api(
        "GET",
        f"/tasks/{owner}/{slug}/runs",
        params={"sort": sort, "view": view, "page": page, "per_page": per_page, "verified_only": verified_only},
    )
    if as_json:
        _json_out(data)
        return
    print_run_table(data, view)
    if data.get("has_next"):
        click.echo(f"  page {page} — more results available (--page {page + 1})")


@run_app.command("view")
def run_view(
    sha: Annotated[str, typer.Argument()],
    as_json: JsonFlag = False,
    task_opt: TaskOpt = None,
):
    """Show a specific run with repo, SHA, branch, and git instructions."""
    _set_task(task_opt)
    ref = _task_ref(get_task())
    owner, slug = _split_task_ref(ref)
    r = _api("GET", f"/tasks/{owner}/{slug}/runs/{sha}")
    if as_json:
        _json_out(r)
        return
    print_run_detail(r)


def _read_fork_json() -> dict:
    """Read .hive/fork.json from the current directory."""
    fork_path = Path(".hive") / "fork.json"
    if not fork_path.exists():
        raise click.ClickException("not in a hive task directory (no .hive/fork.json)")
    return json.loads(fork_path.read_text())


def push_command(task_opt: TaskOpt = None):
    """Push code to the task repo. Works for both public and private tasks."""
    _set_task(task_opt)
    console = get_console()
    fork_info = _read_fork_json()
    mode = fork_info.get("mode", "fork")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")

    # Check for uncommitted changes
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if result.stdout.strip():
        raise click.ClickException(
            "You have uncommitted changes. Commit first:\n"
            "  git add -A && git commit -m \"your description\""
        )

    if mode == "branch":
        # Private task: bundle and upload to server
        ref = _task_ref(get_task())
        owner, slug = _split_task_ref(ref)
        prefix = fork_info.get("branch_prefix", "")
        if prefix and not branch.startswith(prefix):
            raise click.ClickException(
                f"Current branch '{branch}' doesn't start with '{prefix}'.\n"
                f"  Switch to your branch: git checkout {prefix}initial"
            )
        with console.status(f"[bold]Pushing [cyan]{branch}[/cyan] via server...", spinner="dots"):
            # Create git bundle
            with tempfile.NamedTemporaryFile(suffix=".bundle", delete=False) as tmp:
                bundle_path = tmp.name
            try:
                result = subprocess.run(
                    ["git", "bundle", "create", bundle_path, branch, "--not",
                     "--remotes=origin/main", "--remotes=origin/HEAD"],
                    capture_output=True, text=True,
                )
                if result.returncode != 0:
                    # Fallback: bundle all commits on this branch
                    subprocess.run(
                        ["git", "bundle", "create", bundle_path, branch],
                        check=True, capture_output=True, text=True,
                    )
                # Upload bundle to server
                with open(bundle_path, "rb") as f:
                    _api("POST", f"/tasks/{owner}/{slug}/push",
                         data={"branch": branch},
                         files={"bundle": ("bundle.git", f, "application/octet-stream")})
            finally:
                os.unlink(bundle_path)
            # Update remote tracking
            subprocess.run(["git", "fetch", "origin"], capture_output=True, text=True)
        ok(f"Pushed {branch} via server")
    else:
        # Public task: git push directly
        with console.status(f"[bold]Pushing [cyan]{branch}[/cyan]...", spinner="dots"):
            result = subprocess.run(
                ["git", "push", "origin", branch], capture_output=True, text=True
            )
            if result.returncode != 0:
                raise click.ClickException(f"git push failed:\n{result.stderr}")
        ok(f"Pushed {branch}")
