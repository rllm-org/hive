import click
import pytest

from hive.cli.helpers import _parse_since, _config, _task_id


class TestParseSince:
    def test_hours(self):
        result = _parse_since("2h")
        assert "T" in result

    def test_invalid_unit(self):
        with pytest.raises(click.ClickException):
            _parse_since("5x")


class TestConfig:
    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.cli.helpers.CONFIG_PATH", tmp_path / "nope.json")
        assert _config() == {}


class TestTaskId:
    def test_cli_task_param(self):
        assert _task_id(cli_task="my-task") == "my-task"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("HIVE_TASK", "env-task")
        assert _task_id() == "env-task"

    def test_no_task_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HIVE_TASK", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(click.ClickException):
            _task_id()
