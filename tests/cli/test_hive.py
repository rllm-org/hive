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

    def test_register_multiple_agents(self, cli_env):
        result1 = cli_env.invoke(hive, ["auth", "register", "--name", "first"])
        assert result1.exit_code == 0
        result2 = cli_env.invoke(hive, ["auth", "register", "--name", "second"])
        assert result2.exit_code == 0


class TestTaskCreate:
    def test_create(self, cli_env, tmp_path):
        task_dir = tmp_path / "my_task"
        task_dir.mkdir()
        (task_dir / "program.md").write_text("solve it")
        cli_env.invoke(hive, ["auth", "register"])
        result = cli_env.invoke(hive, ["task", "create", "gsm8k",
                                        "--name", "GSM8K Solver",
                                        "--path", str(task_dir),
                                        "--description", "Math benchmark",
                                        "--admin-key", "test-key"])
        assert result.exit_code == 0
        assert "gsm8k" in result.output

    def test_draft_create_does_not_show_in_task_list(self, cli_env, tmp_path):
        task_dir = tmp_path / "my_task"
        task_dir.mkdir()
        (task_dir / "program.md").write_text("solve it")
        cli_env.invoke(hive, ["auth", "register"])
        cli_env.invoke(hive, ["task", "create", "gsm8k",
                               "--name", "GSM8K Solver",
                               "--path", str(task_dir),
                               "--description", "Math benchmark",
                               "--admin-key", "test-key"])
        result = cli_env.invoke(hive, ["task", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output


class TestJsonErrorIntegration:
    def test_whoami_json_error(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "whoami", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert "error" in data

    def test_register_multiple_json(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "first"])
        result = cli_env.invoke(hive, ["auth", "register", "--name", "second", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "second"


class TestAuthStatus:
    def test_status_shows_agents(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-a"])
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-b"])
        result = cli_env.invoke(hive, ["auth", "status"])
        assert result.exit_code == 0
        assert "agent-a" in result.output
        assert "agent-b" in result.output

    def test_status_marks_active(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-a"])
        result = cli_env.invoke(hive, ["auth", "status"])
        assert "agent-a *" in result.output


class TestAuthSwitch:
    def test_switch(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-a"])
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-b"])
        result = cli_env.invoke(hive, ["auth", "switch", "agent-b"])
        assert result.exit_code == 0
        result = cli_env.invoke(hive, ["auth", "whoami"])
        assert result.output.strip() == "agent-b"

    def test_switch_nonexistent_errors(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "switch", "nope"])
        assert result.exit_code != 0


class TestAuthLogout:
    def test_logout(self, cli_env):
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-a"])
        cli_env.invoke(hive, ["auth", "register", "--name", "agent-b"])
        result = cli_env.invoke(hive, ["auth", "unregister", "agent-a"])
        assert result.exit_code == 0
        status = cli_env.invoke(hive, ["auth", "status"])
        assert "agent-a" not in status.output
        assert "agent-b" in status.output


class TestAuthRegister:
    def test_register_alias(self, cli_env):
        result = cli_env.invoke(hive, ["auth", "register", "--name", "my-agent"])
        assert result.exit_code == 0
        assert "my-agent" in result.output


class TestTaskList:
    def test_empty(self, cli_env):
        cli_env.invoke(hive, ["auth", "register"])
        result = cli_env.invoke(hive, ["task", "list"])
        assert result.exit_code == 0
        assert "No tasks" in result.output
