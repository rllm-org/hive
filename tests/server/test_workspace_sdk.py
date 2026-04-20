"""Workspace + agent-sdk: shared sandbox per workspace."""

import time

import pytest
import psycopg
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException

from hive.server.db import init_db, get_db_sync
from tests.conftest import _create_verified_user


def _wait_for_provision(client, headers, wid, timeout_s=2.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        ws = client.get(f"/api/workspaces/{wid}", headers=headers).json()
        if ws.get("sdk_sandbox_id"):
            return ws
        time.sleep(0.05)
    return None


@pytest.fixture
def mock_agent_sdk(monkeypatch):
    m = MagicMock()
    m.provision_sandbox = AsyncMock(return_value={"sandbox_id": "sb-ws-shared"})
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
        w = client.post("/api/workspaces", json={"name": "ws-sandbox", "type": "cloud"}, headers=h)
        assert w.status_code == 200
        wid = w.json()["id"]

        ws = _wait_for_provision(client, h, wid)
        assert ws and ws.get("sdk_sandbox_id") == "sb-ws-shared"
        assert mock_agent_sdk.provision_sandbox.call_count == 1
        assert mock_agent_sdk.create_quick_session.call_count == 0

        r1 = client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        assert r1.status_code == 200
        r2 = client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        assert r2.status_code == 200

        assert mock_agent_sdk.create_quick_session.call_count == 0
        assert mock_agent_sdk.create_session.call_count == 2
        for call_args in mock_agent_sdk.create_session.call_args_list:
            args, _ = call_args
            assert args[0] == "sb-ws-shared"

    def test_delete_workspace_destroys_sandbox_once(self, client, mock_agent_sdk):
        token, _ = _create_verified_user(client, "ws-del@x.com", "password123", handle="ws-del-user")
        h = {"Authorization": f"Bearer {token}"}
        wid = client.post("/api/workspaces", json={"name": "ws-del", "type": "cloud"}, headers=h).json()["id"]
        assert _wait_for_provision(client, h, wid) is not None
        client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)

        d = client.delete(f"/api/workspaces/{wid}", headers=h)
        assert d.status_code == 200
        assert mock_agent_sdk.destroy_sandbox.call_count == 1
        assert mock_agent_sdk.destroy_sandbox.call_args[0][0] == "sb-ws-shared"

    def test_provision_failure_leaves_pending_workspace(self, client, mock_agent_sdk):
        token, _ = _create_verified_user(client, "ws-fail@x.com", "password123", handle="ws-fail-user")
        h = {"Authorization": f"Bearer {token}"}
        mock_agent_sdk.provision_sandbox = AsyncMock(
            side_effect=HTTPException(status_code=502, detail="sdk down")
        )

        r = client.post("/api/workspaces", json={"name": "ws-boom", "type": "cloud"}, headers=h)
        assert r.status_code == 200
        wid = r.json()["id"]
        assert r.json().get("sdk_sandbox_id") is None

        ws = client.get(f"/api/workspaces/{wid}", headers=h).json()
        assert ws.get("sdk_sandbox_id") is None

    def test_cloud_workspace_agent_has_cloud_type(self, client, mock_agent_sdk):
        token, _ = _create_verified_user(client, "ws-type@x.com", "password123", handle="ws-type-user")
        h = {"Authorization": f"Bearer {token}"}
        wid = client.post("/api/workspaces", json={"name": "ws-type", "type": "cloud"}, headers=h).json()["id"]
        assert _wait_for_provision(client, h, wid) is not None
        resp = client.post(f"/api/workspaces/{wid}/agents", json={}, headers=h)
        assert resp.status_code == 200
        agent_id = resp.json()["id"]

        with get_db_sync() as conn:
            row = conn.execute("SELECT type FROM agents WHERE id = %s", (agent_id,)).fetchone()
        assert row["type"] == "cloud"


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
