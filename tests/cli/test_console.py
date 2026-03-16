from rich.console import Console

from hive.cli.console import get_console


def test_get_console_returns_console():
    c = get_console()
    assert isinstance(c, Console)


def test_get_console_highlight_off():
    c = get_console()
    assert c._highlight is False


def test_get_console_returns_new_instance():
    c1 = get_console()
    c2 = get_console()
    assert c1 is not c2
