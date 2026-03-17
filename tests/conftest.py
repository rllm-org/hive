import json
import socket
import threading

import pytest
import uvicorn
from fastapi.testclient import TestClient

from hive.server.db import init_db
from hive.server.main import app
from tests.mocks import MockGitHubApp
from hive.server.github import set_github_app


def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a fresh SQLite DB per test."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setattr("hive.server.db.DATABASE_URL", db_url)
    init_db()
    set_github_app(MockGitHubApp())
    return TestClient(app)


@pytest.fixture()
def mock_github(client):
    from hive.server.github import get_github_app
    return get_github_app()


@pytest.fixture()
def registered_agent(client):
    """Register an agent and return (client, agent_id, token)."""
    resp = client.post("/register")
    data = resp.json()
    return client, data["id"], data["token"]


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    """Start a real uvicorn server on a random port. Returns the base URL."""
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setattr("hive.server.db.DATABASE_URL", db_url)
    init_db()
    set_github_app(MockGitHubApp())

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    import httpx, time
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            httpx.get(f"{url}/tasks", timeout=1)
            break
        except httpx.ConnectError:
            time.sleep(0.1)

    yield url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def cli_env(live_server, tmp_path, monkeypatch):
    """Set up CLI to point at the live test server. Returns (runner, config_path)."""
    import click.testing

    cfg_path = tmp_path / "cli_cfg.json"
    monkeypatch.setattr("hive.cli.helpers.CONFIG_PATH", cfg_path)
    monkeypatch.setenv("HIVE_SERVER", live_server)

    return click.testing.CliRunner()
