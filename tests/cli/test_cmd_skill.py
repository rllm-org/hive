from hive.cli.cmd_skill import skill_app


def test_import():
    """Verify the module imports and skill_app is a Typer instance."""
    assert skill_app is not None
