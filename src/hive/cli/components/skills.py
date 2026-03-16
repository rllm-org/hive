from rich.markup import escape
from rich.panel import Panel

from hive.cli.console import get_console


def print_skills_list(skills: list[dict]):
    """Print a list of skills."""
    console = get_console()
    for s in skills:
        delta = f" [green]+{s['score_delta']:.3f}[/green]" if s.get("score_delta") else ""
        name = escape(s["name"])
        desc = escape(s.get("description", "")[:80])
        console.print(f"  [bold]#{s['id']}[/bold] '{name}'{delta}  {desc}")


def print_skill_detail(skill: dict):
    """Print detailed view of a single skill."""
    console = get_console()
    delta = f" [green]+{skill['score_delta']:.3f}[/green]" if skill.get("score_delta") else ""
    name = escape(skill["name"])
    desc = escape(skill.get("description", ""))
    console.print(f"[bold]#{skill['id']}[/bold] '{name}'{delta}")
    console.print(desc)
    console.print()
    code = skill.get("code_snippet", "")
    if code:
        panel = Panel(code, title="Code", border_style="dim")
        console.print(panel)
    else:
        console.print(code)
