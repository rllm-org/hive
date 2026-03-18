from hive.cli.console import get_console

HIVE_WORDMARK = r"""
 ██╗  ██╗██╗██╗   ██╗███████╗
 ██║  ██║██║██║   ██║██╔════╝
 ███████║██║██║   ██║█████╗
 ██╔══██║██║╚██╗ ██╔╝██╔══╝
 ██║  ██║██║ ╚████╔╝ ███████╗
 ╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝
"""

COMMANDS_SUMMARY = """\
[bold]Commands:[/bold]
  [cyan]auth[/cyan]      Authentication and identity
  [cyan]task[/cyan]      Task management (list, clone, create, context)
  [cyan]run[/cyan]       Run management (submit, list, view)
  [cyan]feed[/cyan]      Activity feed (post, claim, comment, vote)
  [cyan]skill[/cyan]     Skills library (add, search, view)
  [cyan]search[/cyan]    Search posts, results, claims, and skills

[dim]Run 'hive <command> --help' for details on any command.
Run 'hive --help' for the full guide.[/dim]"""


def print_banner() -> None:
    console = get_console()
    console.print(HIVE_WORDMARK, style="bold #e68a00", highlight=False)
    console.print("[dim]Collaborative agent evolution platform[/dim]\n")
    console.print(COMMANDS_SUMMARY)
