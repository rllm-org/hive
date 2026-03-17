from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from hive.cli.console import get_console


def print_leaderboard(entries: list[dict]):
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
        score = f"{r['score']:.4f}" if r.get("score") is not None else "  \u2014   "
        v = "" if r.get("verified") else " \\[unverified]"
        fork_url = r.get("fork_url", "")
        short_fork = fork_url.replace("https://github.com/", "") if fork_url else "--"
        table.add_row(
            str(i),
            score,
            r["id"][:8],
            escape(r["agent_id"]),
            escape(short_fork),
            escape(r.get("tldr", "")) + v,
        )
    console.print(table)


def print_run_table(data: dict, view: str):
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
            score = f"{r['score']:.4f}" if r.get("score") is not None else "  \u2014   "
            v = "verified" if r.get("verified") else "unverified"
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
        table.add_column("Delta", justify="right", width=8)
        table.add_column("From", justify="right", width=8)
        table.add_column("To", justify="right", width=8)
        table.add_column("Agent", style="cyan")
        for e in data.get("entries", []):
            table.add_row(
                e["run_id"][:8],
                f"{e.get('delta', 0):+.4f}",
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


def print_run_detail(r: dict):
    """Print detailed view of a single run."""
    console = get_console()
    score = f"{r['score']:.3f}" if r.get("score") is not None else "\u2014"
    v = "verified" if r.get("verified") else "unverified"
    lines = [
        f"[bold]Run:[/bold]    {escape(r['id'])}",
        f"[bold]Agent:[/bold]  [cyan]{escape(r['agent_id'])}[/cyan]",
        f"[bold]Fork:[/bold]   {escape(r.get('fork_url') or r.get('repo_url') or chr(0x2014))}",
        f"[bold]Branch:[/bold] {escape(r['branch'])}",
        f"[bold]SHA:[/bold]    {escape(r['id'])}",
        f"[bold]Score:[/bold]  [green]{score}[/green]  \\[{v}]",
        f"[bold]TLDR:[/bold]   {escape(r.get('tldr', ''))}",
    ]
    panel = Panel("\n".join(lines), title="Run Detail", border_style="dim")
    console.print(panel)
    fork = r.get("fork_url") or r.get("repo_url", "")
    agent = r.get("agent_id", "remote")
    console.print(f"\nTo build on this run:")
    git_url = fork if fork.endswith(".git") else f"{fork}.git" if fork else ""
    console.print(f"  git remote add {escape(agent)} {escape(git_url)}")
    console.print(f"  git fetch {escape(agent)}")
    console.print(f"  git checkout {escape(r['id'])}")
