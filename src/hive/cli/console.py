from rich.console import Console


def get_console() -> Console:
    """Create a Rich console for CLI output.

    Returns a new Console each call so it picks up the current sys.stdout —
    important when Click's CliRunner patches stdout during tests.
    """
    return Console(highlight=False)
