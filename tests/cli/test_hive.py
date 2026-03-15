"""Tests for CLI commands using Click's CliRunner."""

from unittest.mock import patch, MagicMock

import click.testing
import pytest

from hive.cli.hive import hive, _parse_since


@pytest.fixture()
def runner():
    return click.testing.CliRunner()


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


class TestWhoami:
    def test_not_registered(self, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.hive.CONFIG_PATH", tmp_path / "cfg.json")
        result = runner.invoke(hive, ["whoami"])
        assert result.exit_code != 0

    def test_registered(self, runner, tmp_path, monkeypatch):
        import json
        cfg = tmp_path / "cfg.json"
        cfg.write_text(json.dumps({"agent_id": "cool-bot", "token": "cool-bot"}))
        monkeypatch.setattr("hive.cli.hive.CONFIG_PATH", cfg)
        result = runner.invoke(hive, ["whoami"])
        assert "cool-bot" in result.output


class TestRegister:
    @patch("hive.cli.hive._api")
    def test_register(self, mock_api, runner, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.hive.CONFIG_PATH", tmp_path / "cfg.json")
        mock_api.return_value = {"id": "swift-phoenix", "token": "swift-phoenix"}
        result = runner.invoke(hive, ["register"])
        assert result.exit_code == 0
        assert "swift-phoenix" in result.output


class TestTasks:
    @patch("hive.cli.hive._api")
    def test_empty(self, mock_api, runner):
        mock_api.return_value = {"tasks": []}
        result = runner.invoke(hive, ["tasks"])
        assert "No tasks" in result.output

    @patch("hive.cli.hive._api")
    def test_list(self, mock_api, runner):
        mock_api.return_value = {"tasks": [
            {"id": "t1", "name": "Task 1", "stats": {"best_score": 0.5, "total_runs": 3, "agents_contributing": 2}},
        ]}
        result = runner.invoke(hive, ["tasks"])
        assert "t1" in result.output
