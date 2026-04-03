import importlib
import runpy
import sys


def test_import_does_not_run_init_db(monkeypatch):
    calls: list[str] = []

    def fake_init_db() -> None:
        calls.append("init")

    monkeypatch.setattr("hive.server.db.init_db", fake_init_db)

    import hive.server.migrate as migrate

    importlib.reload(migrate)

    assert calls == []


def test_main_runs_init_db(monkeypatch, capsys):
    calls: list[str] = []

    def fake_init_db() -> None:
        calls.append("init")

    monkeypatch.setattr("hive.server.db.init_db", fake_init_db)
    sys.modules.pop("hive.server.migrate", None)

    runpy.run_module("hive.server.migrate", run_name="__main__")

    assert calls == ["init"]
    assert "Database schema up to date." in capsys.readouterr().out
