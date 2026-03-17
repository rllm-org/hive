from hive.cli.help_text import HIVE_HELP


def test_help_text_exists():
    assert len(HIVE_HELP) > 100


def test_help_text_has_sections():
    assert "SETUP:" in HIVE_HELP
    assert "EXPERIMENT LOOP" in HIVE_HELP
    assert "BUILDING ON ANOTHER" in HIVE_HELP
