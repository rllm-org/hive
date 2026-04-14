import click
import pytest

from hive.cli.helpers import _parse_since, _config, _task_ref, _split_task_ref


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


class TestTaskRef:
    def test_cli_task_param(self):
        assert _task_ref(cli_task="acme/my-task") == "acme/my-task"

    def test_bare_slug_gets_default_owner(self):
        assert _task_ref(cli_task="my-task") == "hive/my-task"

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("HIVE_TASK", "acme/env-task")
        assert _task_ref() == "acme/env-task"

    def test_env_var_bare_slug(self, monkeypatch):
        monkeypatch.setenv("HIVE_TASK", "env-task")
        assert _task_ref() == "hive/env-task"

    def test_no_task_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("HIVE_TASK", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(click.ClickException):
            _task_ref()


class TestSplitTaskRef:
    def test_split(self):
        assert _split_task_ref("acme/my-task") == ("acme", "my-task")
