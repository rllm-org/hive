import json
from pathlib import Path

import click.testing

from hive.cli.app import cli


class TestRootHelp:
    def test_help_output(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Hive" in result.output

    def test_no_args_shows_banner(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "auth" in result.output
        assert "task" in result.output

    def test_help_is_verbose(self):
        runner = click.testing.CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        # Full help text should be significantly longer than the banner
        assert len(result.output) > 200


class TestJsonError:
    def test_json_error_on_missing_token(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.helpers.CONFIG_PATH", tmp_path / "cfg.json")
        runner = click.testing.CliRunner(env={"HIVE_SERVER": "http://localhost:1"})
        result = runner.invoke(cli, ["auth", "whoami", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data

    def test_non_json_error_without_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.helpers.CONFIG_PATH", tmp_path / "cfg.json")
        runner = click.testing.CliRunner(env={"HIVE_SERVER": "http://localhost:1"})
        result = runner.invoke(cli, ["auth", "whoami"])
        assert result.exit_code != 0
        # Should NOT be JSON
        assert not result.output.strip().startswith("{")
