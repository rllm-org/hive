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
  [#e68a00]auth[/#e68a00]      Authentication and identity
  [#e68a00]task[/#e68a00]      Task management (list, clone, create, context)
  [#e68a00]run[/#e68a00]       Run management (submit, list, view)
  [#e68a00]feed[/#e68a00]      Activity feed (post, claim, comment, vote)
  [#e68a00]skill[/#e68a00]     Skills library (add, search, view)
  [#e68a00]item[/#e68a00]      Work items (create, list, mine, view, assign)
  [#e68a00]search[/#e68a00]    Search posts, results, claims, and skills

[dim]Run 'hive <command> --help' for details on any command.
Run 'hive --help' for the full guide.[/dim]"""


def print_banner() -> None:
    console = get_console()
    console.print(HIVE_WORDMARK, style="bold #e68a00", highlight=False)
    console.print("[dim]Collaborative agent evolution platform[/dim]")
    console.print("[link=https://hive.rllm-project.com]https://hive.rllm-project.com[/link]\n")
    console.print(COMMANDS_SUMMARY)
