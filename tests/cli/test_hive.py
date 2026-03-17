"""CLI tests against a real running server — no mocks."""

import json

import click
import pytest

from hive.cli.hive import hive, _parse_since


class TestParseSince:
    def test_hours(self):
        result = _parse_since("2h")
        assert "T" in result

    def test_minutes(self):
        result = _parse_since("30m")
        assert "T" in result

    def test_days(self):
        result = _parse_since("1d")
        assert "T" in result

    def test_invalid_unit(self):
        with pytest.raises(click.ClickException):
            _parse_since("5x")

    def test_invalid_number(self):
        with pytest.raises(click.ClickException):
            _parse_since("abch")


class TestAuthWhoami:
    def test_not_registered(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "whoami"])
        assert result.exit_code != 0

    def test_after_register(self, cli_env):
        cli_env.invoke(hive, ["auth", "register"])
        result = cli_env.invoke(hive, ["auth", "whoami"])
        assert result.exit_code == 0
        assert result.output.strip()


class TestAuthRegister:
    def test_register(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "register"])
        assert result.exit_code == 0
        assert "Registered as:" in result.output

    def test_register_with_name(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "register", "--name", "my-agent"])
        assert result.exit_code == 0
        assert "my-agent" in result.output

    def test_register_twice_errors(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "first"])
        result = cli_env.invoke(hive, ["auth", "register", "--name", "second"])
        assert result.exit_code != 0
        assert "Already registered" in result.output


class TestTaskCreate:
    def test_create(self, cli_env, tmp_path):
        task_dir = tmp_path / "my_task"
        task_dir.mkdir()
        (task_dir / "program.md").write_text("solve it")
        cli_env.invoke(hive, ["auth", "register"])
        result = cli_env.invoke(hive, ["task", "create", "gsm8k",
                                        "--name", "GSM8K Solver",
                                        "--path", str(task_dir),
                                        "--description", "Math benchmark"])
        assert result.exit_code == 0
        assert "gsm8k" in result.output

    def test_shows_in_list(self, cli_env, tmp_path):
        task_dir = tmp_path / "my_task"
        task_dir.mkdir()
        (task_dir / "program.md").write_text("solve it")
        cli_env.invoke(hive, ["auth", "register"])
        cli_env.invoke(hive, ["task", "create", "gsm8k",
                               "--name", "GSM8K Solver",
                               "--path", str(task_dir),
                               "--description", "Math benchmark"])
        result = cli_env.invoke(hive, ["task", "list"])
        assert "gsm8k" in result.output
        assert "GSM8K Solver" in result.output


class TestJsonErrorIntegration:
    def test_whoami_json_error(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "whoami", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data

    def test_register_twice_json_error(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "first"])
        result = cli_env.invoke(hive, ["auth", "register", "--name", "second", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data
        assert "Already registered" in data["error"]


class TestTaskList:
    def test_empty(self, cli_env):
        cli_env.invoke(hive, ["auth", "register"])
        result = cli_env.invoke(hive, ["task", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output
