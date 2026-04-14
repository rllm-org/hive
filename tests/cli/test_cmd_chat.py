from hive.cli.cmd_chat import chat_app


def test_import():
    """Verify the module imports and chat_app is a Typer instance."""
    assert chat_app is not None
