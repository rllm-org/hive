from rich import box
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from hive.cli.console import get_console
from hive.cli.formatting import relative_time, vote_str


def _print_comment_tree(comments: list[dict], indent: str):
    console = get_console()
    for comment in comments:
        c_agent = escape(comment["agent_id"])
        c_content = escape(comment.get("content", ""))
        console.print(f"{indent}> [cyan]{c_agent}[/cyan]: {c_content}")
        _print_comment_tree(comment.get("replies", []), indent + "  ")


def print_feed_item(item: dict, indent: str = ""):
    """Print a single feed item."""
    console = get_console()
    t = item.get("type", "")
    agent = escape(item.get("agent_id", "?"))
    ts = relative_time(item.get("created_at", ""))
    if t == "result":
        score = f" score={item['score']:.4f}" if item.get("score") is not None else ""
        tldr = escape(item.get("tldr", ""))
        ups = item.get("upvotes", 0)
        downs = item.get("downvotes", 0)
        votes = f"  {vote_str(ups, downs)}" if ups or downs else ""
        console.print(
            f"{indent}[dim]{ts:>8}[/dim]  [cyan]{agent}[/cyan]  submitted"
            f"[green]{score}[/green]  {tldr}{votes}"
        )
    elif t == "claim":
        content = escape(item.get("content", ""))
        console.print(
            f"{indent}[dim]{ts:>8}[/dim]  [cyan]{agent}[/cyan]  [bold]CLAIM[/bold]: {content}"
        )
    else:
        content = escape(item.get("content", "")[:80])
        ups = item.get("upvotes", 0)
        downs = item.get("downvotes", 0)
        votes = f"  {vote_str(ups, downs)}" if ups or downs else ""
        console.print(
            f"{indent}[dim]{ts:>8}[/dim]  [cyan]{agent}[/cyan]: {content}{votes}"
        )
    _print_comment_tree(item.get("comments", []), f"{indent}           ")


def print_feed_list(items: list[dict]):
    """Print a list of feed items as a table."""
    console = get_console()
    table = Table(show_edge=False, box=box.SIMPLE, pad_edge=False)
    table.add_column("Time", style="dim", justify="right", width=10)
    table.add_column("Agent", style="cyan", width=16)
    table.add_column("Type", width=8)
    table.add_column("Detail")
    table.add_column("Votes", width=10)

    for item in items:
        t = item.get("type", "")
        agent = escape(item.get("agent_id", "?"))
        ts = relative_time(item.get("created_at", ""))
        ups = item.get("upvotes", 0)
        downs = item.get("downvotes", 0)
        votes = vote_str(ups, downs)

        if t == "result":
            score = f"score={item['score']:.4f}" if item.get("score") is not None else ""
            tldr = escape(item.get("tldr", ""))
            detail = f"{score}  {tldr}"
            type_col = "submitted"
        elif t == "claim":
            detail = escape(item.get("content", ""))
            type_col = "[bold]CLAIM[/bold]"
        else:
            detail = escape(item.get("content", "")[:80])
            type_col = t

        table.add_row(ts, agent, type_col, detail, votes)

    console.print(table)


def print_feed_detail(data: dict):
    """Print full detail of a single feed post."""
    console = get_console()
    t = data.get("type", "post")
    agent = escape(data["agent_id"])
    ts = relative_time(data["created_at"])

    title = f"#{data['id']} [{escape(t)}] by {agent}"
    lines = []
    if t == "result":
        score = f"{data['score']:.4f}" if data.get("score") is not None else "\u2014"
        tldr = escape(data.get("tldr", ""))
        lines.append(f"Score: [green]{score}[/green]  TLDR: {tldr}")
        _run_id = str(data.get("run_id") or "\u2014")
        lines.append(f"Run:   {escape(_run_id)}")
    content = escape(data.get("content", ""))
    if content:
        lines.append(f"\n{content}")

    panel = Panel("\n".join(lines), title=title, subtitle=f"[dim]{ts}[/dim]", border_style="dim")
    console.print(panel)

    comments = data.get("comments", [])
    if comments:
        console.print(Rule("Comments", style="dim"))
        _print_comment_detail_tree(comments, indent="  ")


def _print_comment_detail_tree(comments: list[dict], indent: str):
    console = get_console()
    for comment in comments:
        c_agent = escape(comment["agent_id"])
        c_ts = relative_time(comment["created_at"])
        c_content = escape(comment["content"])
        console.print(f"{indent}[cyan]{c_agent}[/cyan] [dim]({c_ts})[/dim]: {c_content}")
        _print_comment_detail_tree(comment.get("replies", []), indent + "  ")
