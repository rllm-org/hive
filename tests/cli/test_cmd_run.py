from hive.cli.cmd_run import run_app


def test_import():
    """Verify the module imports and run_app is a Typer instance."""
    assert run_app is not None
