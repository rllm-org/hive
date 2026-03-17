from hive.cli.state import _set_task, get_task, set_json_mode, is_json_mode
import hive.cli.state as state_mod


class TestSetTask:
    def test_set_and_get(self):
        state_mod._cli_task = None
        _set_task("my-task")
        assert get_task() == "my-task"

    def test_none_does_not_overwrite(self):
        state_mod._cli_task = None
        _set_task("first")
        _set_task(None)
        assert get_task() == "first"

    def test_get_returns_none_initially(self):
        state_mod._cli_task = None
        assert get_task() is None


class TestJsonMode:
    def test_default_off(self):
        state_mod._json_mode = False
        assert is_json_mode() is False

    def test_set_on(self):
        set_json_mode(True)
        assert is_json_mode() is True
        set_json_mode(False)

    def test_set_off(self):
        set_json_mode(True)
        set_json_mode(False)
        assert is_json_mode() is False
