from hive.cli.banner import HIVE_WORDMARK, COMMANDS_SUMMARY, print_banner


class TestBannerConstants:
    def test_wordmark_contains_hive(self):
        assert "██" in HIVE_WORDMARK

    def test_commands_summary_lists_commands(self):
        for cmd in ("auth", "task", "run", "feed", "skill", "search"):
            assert cmd in COMMANDS_SUMMARY

    def test_commands_summary_has_help_hint(self):
        assert "hive --help" in COMMANDS_SUMMARY


class TestPrintBanner:
    def test_print_banner_runs(self, capsys):
        print_banner()
        captured = capsys.readouterr()
        assert "auth" in captured.out
        assert "task" in captured.out
