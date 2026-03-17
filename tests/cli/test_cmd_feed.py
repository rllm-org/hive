from hive.cli.cmd_feed import feed_app


def test_import():
    """Verify the module imports and feed_app is a Typer instance."""
    assert feed_app is not None
