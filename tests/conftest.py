import os
import socket
import threading

import pytest
import uvicorn
from fastapi.testclient import TestClient

from hive.server.db import init_db
from hive.server.main import app
from tests.mocks import MockGitHubApp
from hive.server.github import set_github_app

_ALL_TABLES = "password_resets, oauth_states, pending_signups, item_comments, items, votes, comments, claims, skills, posts, runs, forks, agents, tasks, users"


def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def _pg_test_url():
    """Create a temporary PostgreSQL database for the test session."""
    db_name = f"hive_test_{os.getpid()}"
    try:
        import psycopg
        conn = psycopg.connect("postgresql://localhost:5432/postgres", autocommit=True)
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.execute(f"CREATE DATABASE {db_name}")
        conn.close()
    except Exception:
        yield None
        return
    yield f"postgresql://localhost:5432/{db_name}"
    try:
        import psycopg
        conn = psycopg.connect("postgresql://localhost:5432/postgres", autocommit=True)
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.close()
    except Exception:
        pass


@pytest.fixture()
def client(monkeypatch, _pg_test_url):
    """TestClient with a fresh DB per test, runs against PostgreSQL."""
    if _pg_test_url is None:
        pytest.skip("PostgreSQL not available")
    db_url = _pg_test_url
    monkeypatch.setattr("hive.server.db.DATABASE_URL", db_url)
    monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
    monkeypatch.setattr("hive.server.main.JWT_SECRET", "test-jwt-secret")
    init_db()
    import psycopg
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE")
    set_github_app(MockGitHubApp())
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def mock_github(client):
    from hive.server.github import get_github_app
    return get_github_app()


@pytest.fixture()
def registered_agent(client):
    """Register an agent and return (client, agent_id, token)."""
    resp = client.post("/api/register")
    data = resp.json()
    return client, data["id"], data["token"]


def _create_verified_user(client, email, password):
    """Helper: signup + verify code flow. Returns (token, user_data)."""
    from hive.server.db import get_db_sync
    client.post("/api/auth/signup", json={"email": email, "password": password})
    with get_db_sync() as conn:
        row = conn.execute("SELECT code FROM pending_signups WHERE email = %s", (email,)).fetchone()
    resp = client.post("/api/auth/verify-code", json={"email": email, "code": row["code"]})
    data = resp.json()
    return data["token"], data["user"]


@pytest.fixture()
def auth_user(client):
    """Sign up a test user and return (client, jwt_token, user_data)."""
    token, user = _create_verified_user(client, "test@example.com", "testpass123")
    return client, token, user


@pytest.fixture()
def admin_user(client):
    """Sign up a user and promote to admin. Returns (client, jwt_token, user_data)."""
    _create_verified_user(client, "admin@example.com", "adminpass123")
    from hive.server.db import get_db_sync
    with get_db_sync() as conn:
        conn.execute("UPDATE users SET role = 'admin' WHERE email = %s", ("admin@example.com",))
    # Re-login to get fresh JWT with admin role
    resp = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "adminpass123"})
    data = resp.json()
    return client, data["token"], data["user"]


@pytest.fixture()
def live_server(monkeypatch, _pg_test_url):
    """Start a real uvicorn server on a random port. Returns the base URL."""
    if _pg_test_url is None:
        pytest.skip("PostgreSQL not available")
    db_url = _pg_test_url
    monkeypatch.setattr("hive.server.db.DATABASE_URL", db_url)
    monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
    monkeypatch.setattr("hive.server.main.JWT_SECRET", "test-jwt-secret")
    init_db()
    import psycopg
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {_ALL_TABLES} RESTART IDENTITY CASCADE")
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
            httpx.get(f"{url}/api/tasks", timeout=1)
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
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    monkeypatch.setattr("hive.server.main.ADMIN_KEY", "test-key")
    monkeypatch.setattr("hive.cli.helpers.CONFIG_PATH", cfg_path)
    monkeypatch.setattr("hive.cli.helpers.AGENTS_DIR", agents_dir)
    monkeypatch.setenv("HIVE_SERVER", live_server)
    monkeypatch.setenv("HIVE_ADMIN_KEY", "test-key")

    return click.testing.CliRunner()
