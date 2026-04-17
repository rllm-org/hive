"""Workspace + agent-sdk: shared sandbox per workspace."""

import pytest
import psycopg
from unittest.mock import AsyncMock, MagicMock

from hive.server.db import init_db, get_db_sync
from tests.conftest import _create_verified_user


@pytest.fixture
def mock_agent_sdk(monkeypatch):
    m = MagicMock()
    m.create_quick_session = AsyncMock(
        return_value={
            "sandbox_id": "sb-ws-shared",
            "session_id": "sess-quick-1",
            "agent_id": "ga-1",
            "inner_session_id": "in-1",
            "connected": True,
        }
    )
    m.create_session = AsyncMock(
        return_value={
            "sandbox_id": "sb-ws-shared",
            "session_id": "sess-on-shared-2",
            "agent_id": "ga-2",
            "inner_session_id": "in-2",
            "connected": True,
        }
    )
    m.destroy_sandbox = AsyncMock()
    m.delete_session = AsyncMock()
    monkeypatch.setattr("hive.server.agent_sdk_client.AGENT_SDK_BASE_URL", "http://sdk.test")
    monkeypatch.setattr("hive.server.agent_sdk_client.get_client", lambda: m)
    return m


class TestWorkspaceSharedSandbox:
    def test_second_agent_uses_create_session(self, client, mock_agent_sdk):
        token, _ = _create_verified_user(client, "ws-sdk@x.com", "password123", handle="ws-sdk-user")
        h = {"Authorization": f"Bearer {token}"}
        w = client.post("/api/workspaces", json={"name": "ws-sandbox", "type": "local"}, headers=h)
        assert w.status_code == 200
        wid = w.json()["id"]

        r1 = client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        assert r1.status_code == 200
        r2 = client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        assert r2.status_code == 200

        assert mock_agent_sdk.create_quick_session.call_count == 1
        assert mock_agent_sdk.create_session.call_count == 1
        args, _kw = mock_agent_sdk.create_session.call_args
        assert args[0] == "sb-ws-shared"

    def test_delete_workspace_destroys_sandbox_once(self, client, mock_agent_sdk):
        token, _ = _create_verified_user(client, "ws-del@x.com", "password123", handle="ws-del-user")
        h = {"Authorization": f"Bearer {token}"}
        wid = client.post("/api/workspaces", json={"name": "ws-del", "type": "local"}, headers=h).json()["id"]
        client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)

        d = client.delete(f"/api/workspaces/{wid}", headers=h)
        assert d.status_code == 200
        assert mock_agent_sdk.destroy_sandbox.call_count == 1
        assert mock_agent_sdk.destroy_sandbox.call_args[0][0] == "sb-ws-shared"


class TestWorkspaceSandboxMigration:
    def test_migration_drops_workspace_sdk_session_id(self, monkeypatch, _pg_test_url):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        init_db()
        with psycopg.connect(_pg_test_url, autocommit=True) as c:
            c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS sdk_session_id TEXT")
        init_db()
        with get_db_sync() as conn:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'workspaces'"
            ).fetchall()
        names = {r["column_name"] for r in rows}
        assert "sdk_session_id" not in names
        assert "sdk_sandbox_id" in names
        assert "sdk_base_url" in names
