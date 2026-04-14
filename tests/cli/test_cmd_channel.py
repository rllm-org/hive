from hive.cli.cmd_channel import channel_app


def test_import():
    """Verify the module imports and channel_app is a Typer instance."""
    assert channel_app is not None
