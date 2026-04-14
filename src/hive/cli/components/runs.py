from typing import Any

from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from hive.cli.console import get_console
from hive.cli.formatting import delta_str


_RANK_STYLES = {1: "[bold yellow]1[/bold yellow]", 2: "[bold]2[/bold]", 3: "[bold]3[/bold]"}


def _display_score_value(run: dict[str, Any]) -> float | None:
    """Pick the score column that should be shown to the user."""

    if run.get("verified_score") is not None:
        return run.get("verified_score")
    return run.get("score")


def _display_score_text(run: dict[str, Any], *, width: int = 8, precision: int = 4) -> str:
    """Format the display score while preserving the existing empty-state width."""

    value = _display_score_value(run)
    if value is None:
        return "  \u2014   " if width == 8 else "\u2014"
    return f"{value:.{precision}f}"


def _verification_label(run: dict[str, Any]) -> str:
    """Convert verification fields into the short label shown in tables."""

    status = run.get("verification_status")
    if status == "success" or run.get("verified"):
        return "verified"
    if status in {"pending", "running", "failed", "error"}:
        return status
    return "unverified"


def print_leaderboard(entries: list[dict[str, Any]]) -> None:
    """Print leaderboard table (used in task context)."""
    console = get_console()
    if not entries:
        console.print("  No runs yet. Be the first to submit!")
        return
    table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Score", style="green", justify="right", width=8)
    table.add_column("SHA", width=10)
    table.add_column("Agent", style="cyan", width=20)
    table.add_column("Fork", style="dim", no_wrap=True)
    table.add_column("TLDR")
    for i, r in enumerate(entries, 1):
        score = _display_score_text(r)
        v = f" \\[{_verification_label(r)}]"
        fork_url = r.get("fork_url", "")
        short_fork = fork_url.replace("https://github.com/", "") if fork_url else "--"
        rank = _RANK_STYLES.get(i, str(i))
        table.add_row(
            rank,
            score,
            r["id"][:8],
            escape(r["agent_id"]),
            escape(short_fork),
            escape(r.get("tldr", "")) + v,
        )
    console.print(table)


def print_run_table(data: dict[str, Any], view: str) -> None:
    """Print run list table for any of the 4 view modes."""
    console = get_console()
    if view == "best_runs":
        table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
        table.add_column("SHA", width=10)
        table.add_column("Score", style="green", justify="right", width=8)
        table.add_column("Status", justify="right", width=12)
        table.add_column("Agent", style="cyan", width=20)
        table.add_column("TLDR")
        for r in data.get("runs", []):
            score = _display_score_text(r)
            v = _verification_label(r)
            table.add_row(
                r["id"][:8],
                score,
                v,
                escape(r["agent_id"]),
                escape(r.get("tldr", "")),
            )
        console.print(table)
    elif view == "contributors":
        table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
        table.add_column("Agent", style="cyan", width=20)
        table.add_column("Runs", justify="right", width=5)
        table.add_column("Best", style="green", justify="right", width=8)
        table.add_column("Improvements", justify="right", width=12)
        for e in data.get("entries", []):
            best = f"{e['best_score']:.4f}" if e.get("best_score") is not None else "  \u2014   "
            table.add_row(
                escape(e["agent_id"]),
                str(e.get("total_runs", 0)),
                best,
                str(e.get("improvements", 0)),
            )
        console.print(table)
    elif view == "deltas":
        table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
        table.add_column("SHA", width=10)
        table.add_column("Delta", justify="right", width=10)
        table.add_column("From", justify="right", width=8)
        table.add_column("To", justify="right", width=8)
        table.add_column("Agent", style="cyan")
        for e in data.get("entries", []):
            table.add_row(
                e["run_id"][:8],
                delta_str(e.get("delta", 0)),
                f"{e.get('from_score', 0):.4f}",
                f"{e.get('to_score', 0):.4f}",
                escape(e["agent_id"]),
            )
        console.print(table)
    elif view == "improvers":
        table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
        table.add_column("Agent", style="cyan", width=20)
        table.add_column("Improvements", justify="right", width=12)
        table.add_column("Best", style="green", justify="right", width=8)
        for e in data.get("entries", []):
            best = f"{e['best_score']:.4f}" if e.get("best_score") is not None else "  \u2014   "
            table.add_row(
                escape(e["agent_id"]),
                str(e.get("improvements_to_best", 0)),
                best,
            )
        console.print(table)


def print_run_detail(r: dict[str, Any]) -> None:
    """Print detailed view of a single run."""
    console = get_console()
    reported_score = f"{r['score']:.3f}" if r.get("score") is not None else "\u2014"
    verified_score = f"{r['verified_score']:.3f}" if r.get("verified_score") is not None else "\u2014"
    status = _verification_label(r)
    lines = [
        f"[bold]Run:[/bold]    {escape(r['id'])}",
        f"[bold]Agent:[/bold]  [cyan]{escape(r['agent_id'])}[/cyan]",
        f"[bold]Fork:[/bold]   {escape(r.get('fork_url') or r.get('repo_url') or chr(0x2014))}",
        f"[bold]Branch:[/bold] {escape(r['branch'])}",
        f"[bold]SHA:[/bold]    {escape(r['id'])}",
        f"[bold]Status:[/bold] {escape(status)}",
        f"[bold]Score:[/bold]  [green]{reported_score}[/green]  [dim](reported)[/dim]",
        f"[bold]TLDR:[/bold]   {escape(r.get('tldr', ''))}",
    ]
    if "verified_score" in r or "verification_status" in r:
        lines.insert(6, f"[bold]Verified:[/bold] [green]{verified_score}[/green]")
    panel = Panel("\n".join(lines), title="Run Detail", border_style="dim")
    console.print(panel)
    fork = r.get("fork_url") or r.get("repo_url", "")
    agent = r.get("agent_id", "remote")
    git_url = fork if fork.endswith(".git") else f"{fork}.git" if fork else ""
    git_cmds = (
        f"git remote add {escape(agent)} {escape(git_url)}\n"
        f"git fetch {escape(agent)}\n"
        f"git checkout {escape(r['id'])}"
    )
    git_panel = Panel(
        Syntax(git_cmds, "bash"),
        title="Build on this run", border_style="cyan",
    )
    console.print(git_panel)
