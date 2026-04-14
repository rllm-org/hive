from hive.cli.help_text import HIVE_HELP


def test_help_text_exists():
    assert len(HIVE_HELP) > 100


def test_help_text_has_sections():
    assert "COMMANDS:" in HIVE_HELP
    assert "Auth:" in HIVE_HELP
    assert "Runs:" in HIVE_HELP
    assert "Chat:" in HIVE_HELP
