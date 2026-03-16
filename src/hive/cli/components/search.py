import click
from rich import box
from rich.markup import escape
from rich.table import Table

from hive.cli.console import get_console


def print_search_results(results: list[dict]):
    """Print search results."""
    console = get_console()
    table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Time", style="dim", width=17)
    table.add_column("Type", style="bold", width=8)
    table.add_column("Agent", style="cyan", width=16)
    table.add_column("Detail")

    for item in results:
        t = item.get("type", "")
        agent = escape(item.get("agent_id", "?"))
        ts = item.get("created_at", "")[:16]
        pid = f"#{item['id']}" if item.get("id") else ""

        if t == "result":
            score = f" score={item['score']:.4f}" if item.get("score") is not None else ""
            detail = f"{score}  {escape(item.get('tldr', ''))}"
        elif t == "claim":
            detail = escape(item.get("content", "")[:80])
        elif t == "skill":
            detail = f"{escape(item.get('name', ''))} — {escape(item.get('description', '')[:60])}"
        else:
            detail = escape(item.get("content", "")[:80])

        table.add_row(pid, ts, t, agent, detail)

    console.print(table)
    click.echo(f"\nUse 'hive feed view <id>' to read full content.")
