import pytest
from fastapi.testclient import TestClient

from hive.server.db import init_db, DB_PATH
from hive.server.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient with a fresh in-memory-like SQLite DB per test."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("hive.server.db.DB_PATH", db_path)
    init_db()
    return TestClient(app)


@pytest.fixture()
def registered_agent(client):
    """Register an agent and return (client, agent_id, token)."""
    resp = client.post("/register")
    data = resp.json()
    return client, data["id"], data["token"]
