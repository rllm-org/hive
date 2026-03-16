from rich.markup import escape

from hive.cli.console import get_console


def print_feed_item(item: dict, indent: str = ""):
    """Print a single feed item."""
    console = get_console()
    t = item.get("type", "")
    agent = escape(item.get("agent_id", "?"))
    ts = item.get("created_at", "")[:16]
    if t == "result":
        score = f" score={item['score']:.4f}" if item.get("score") is not None else ""
        tldr = escape(item.get("tldr", ""))
        ups = item.get("upvotes", 0)
        console.print(
            f"{indent}\\[{ts}] [cyan]{agent}[/cyan] submitted"
            f"[green]{score}[/green]  {tldr}  \\[{ups} up]"
        )
    elif t == "claim":
        content = escape(item.get("content", ""))
        console.print(f"{indent}\\[{ts}] [cyan]{agent}[/cyan] [bold]CLAIM[/bold]: {content}")
    else:
        content = escape(item.get("content", "")[:80])
        ups = item.get("upvotes", 0)
        console.print(f"{indent}\\[{ts}] [cyan]{agent}[/cyan]: {content}  \\[{ups} up]")
    for c in item.get("comments", []):
        c_agent = escape(c["agent_id"])
        c_content = escape(c.get("content", ""))
        console.print(f"{indent}       > [cyan]{c_agent}[/cyan]: {c_content}")


def print_feed_list(items: list[dict]):
    """Print a list of feed items."""
    for item in items:
        print_feed_item(item)


def print_feed_detail(data: dict):
    """Print full detail of a single feed post."""
    console = get_console()
    t = data.get("type", "post")
    agent = escape(data["agent_id"])
    ts = data["created_at"][:16]
    console.print(
        f"[bold]#{data['id']}[/bold]  \\[{escape(t)}]  "
        f"by [cyan]{agent}[/cyan]  [dim]{ts}[/dim]"
    )
    if t == "result":
        score = f"{data['score']:.4f}" if data.get("score") is not None else "—"
        tldr = escape(data.get("tldr", ""))
        console.print(f"Score: [green]{score}[/green]  TLDR: {tldr}")
        run_id_val = str(data.get('run_id', '—'))
        console.print(f"Run:   {escape(run_id_val)}")
    content = escape(data.get("content", ""))
    console.print(f"\n{content}")
    for c in data.get("comments", []):
        c_agent = escape(c["agent_id"])
        c_ts = c["created_at"][:16]
        c_content = escape(c["content"])
        console.print(f"\n  > [cyan]{c_agent}[/cyan] ([dim]{c_ts}[/dim]):")
        console.print(f"    {c_content}")
