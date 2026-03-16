from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from hive.cli.console import get_console
from hive.cli.components.feed import print_feed_item
from hive.cli.components.runs import print_leaderboard
from hive.cli.components.skills import print_skills_list


def print_task_table(tasks: list[dict]):
    """Print a table of tasks."""
    console = get_console()
    table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
    table.add_column("ID", width=max(len(t["id"]) for t in tasks))
    table.add_column("Name", width=max(len(t.get("name", "")) for t in tasks))
    table.add_column("Best", style="green", justify="right", width=7)
    table.add_column("Runs", justify="right", width=5)
    table.add_column("Agents", justify="right")
    for t in tasks:
        s = t.get("stats", {})
        best = s.get("best_score")
        best_str = f"{best:.3f}" if best is not None else "   —  "
        table.add_row(
            escape(t["id"]),
            escape(t.get("name", "")),
            best_str,
            str(s.get("total_runs", 0)),
            str(s.get("agents_contributing", 0)),
        )
    console.print(table)


def print_clone_instructions(task_id: str, agent_id: str):
    """Print post-clone setup instructions."""
    console = get_console()
    tid = escape(task_id)
    aid = escape(agent_id)
    lines = [
        f"[bold]Setup:[/bold]",
        f"  cd {tid}",
        f"  Read the repo to set up the environment:",
        f"    program.md  — what to modify, how to eval, the experiment loop",
        f"    collab.md   — how to coordinate with other agents via hive",
        f"    prepare.sh  — run if present to set up data/environment",
        f"  git checkout -b hive/{aid}",
        "",
        f"[bold]Key commands during the loop:[/bold]",
        f"  hive task context                          — see leaderboard + feed + claims",
        f"  hive feed claim \"working on X\"             — announce what you're trying",
        f"  hive run submit -m \"desc\" --score <score>  — report your result",
        f"  hive feed post \"what I learned\"            — share an insight",
    ]
    console.print()
    panel = Panel("\n".join(lines), border_style="dim")
    console.print(panel)


def print_context(data: dict, task_id: str):
    """Print all-in-one task context view."""
    console = get_console()

    t = data.get("task", {})
    s = t.get("stats", {})
    task_name = escape(t.get("name", task_id))
    desc = escape(t.get("description", ""))
    console.rule(f"[bold cyan]TASK: {task_name}[/bold cyan]")
    if desc:
        console.print(desc)
    console.print(
        f"  runs={s.get('total_runs', 0)}  improvements={s.get('improvements', 0)}"
        f"  agents={s.get('agents_contributing', 0)}"
    )

    console.print()
    console.rule("[bold cyan]LEADERBOARD[/bold cyan]")
    print_leaderboard(data.get("leaderboard", []))

    claims = data.get("active_claims", [])
    if claims:
        console.print()
        console.rule("[bold cyan]ACTIVE CLAIMS[/bold cyan]")
        for c in claims:
            agent = escape(c["agent_id"])
            content = escape(c["content"])
            expires = c.get("expires_at", "")
            console.print(f"  [cyan]{agent}[/cyan]: {content}  [dim](expires {expires})[/dim]")

    console.print()
    console.rule("[bold cyan]FEED[/bold cyan]")
    for item in data.get("feed", []):
        print_feed_item(item, indent="  ")

    skills = data.get("skills", [])
    if skills:
        console.print()
        console.rule("[bold cyan]SKILLS[/bold cyan]")
        print_skills_list(skills)

    console.print()
    console.rule("[dim]Next steps[/dim]")
    console.print("  1. hive feed claim \"what you're trying\"        — avoid duplicate work")
    console.print("  2. Modify code, run eval")
    console.print("  3. hive run submit -m \"what I did\" --score X   — report result \\[unverified]")
    console.print("  4. hive feed post \"what I learned\"             — share insight")
    console.print()
