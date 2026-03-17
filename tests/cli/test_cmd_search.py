from hive.cli.cmd_search import register_search


def test_import():
    """Verify the module imports and register_search is callable."""
    assert callable(register_search)
