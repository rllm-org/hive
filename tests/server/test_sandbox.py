"""Tests for private-task sandbox APIs."""

from unittest.mock import AsyncMock, patch

from hive.server.crypto import encrypt_value
from hive.server.db import get_db_sync, now
from tests.server.test_private_tasks import _create_user_with_github, _seed_private_task


def _connect_provider(uid, provider="claude_code", credential="sk-ant-test-key"):
    """Insert a connected agent connection for the user."""
    with get_db_sync() as conn:
        ts = now()
        conn.execute(
            """INSERT INTO user_agent_connections
               (user_id, provider, auth_mode, status, encrypted_credential_ref, created_at, updated_at)
               VALUES (%s, %s, 'api_key', 'connected', %s, %s, %s)
               ON CONFLICT (user_id, provider) DO UPDATE SET
                 encrypted_credential_ref = EXCLUDED.encrypted_credential_ref,
                 status = 'connected', updated_at = EXCLUDED.updated_at""",
            (uid, provider, encrypt_value(credential), ts, ts),
        )


def _mock_daytona(monkeypatch):
    """Set env var and patch Daytona so ensure_sandbox provisions inline."""
    monkeypatch.setenv("DAYTONA_API_KEY", "fake-key")
    mock_box = type("Box", (), {"id": "daytona-test-123"})()
    mock_create = AsyncMock(return_value=mock_box)
    mock_daytona_ctx = AsyncMock()
    mock_daytona_ctx.__aenter__ = AsyncMock(return_value=mock_daytona_ctx)
    mock_daytona_ctx.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("hive.server.sandbox_routes.AsyncDaytona", lambda: mock_daytona_ctx)
    monkeypatch.setattr("hive.server.sandbox_routes.create_sandbox_interactive", mock_create)
    # Also mock for stop
    mock_daytona_ctx.get = AsyncMock(return_value=mock_box)
    mock_daytona_ctx.stop = AsyncMock()
    return mock_create


class TestSandboxAPI:
    def test_sandbox_requires_auth(self, client):
        _jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-task")
        r = client.post("/api/tasks/sb-task/sandbox", json={"provider": "claude_code"})
        assert r.status_code == 401

    def test_sandbox_public_task_rejected(self, client):
        jwt, uid = _create_user_with_github(client)
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO tasks (id, name, description, repo_url, config, created_at, task_type, visibility)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                ("pub-sb", "P", "D", "https://github.com/o/r", "{}", now(), "public", "public"),
            )
        r = client.post(
            "/api/tasks/pub-sb/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 400

    def test_sandbox_create_and_get(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-own")
        r = client.post(
            "/api/tasks/sb-own/sandbox",
            json={"provider": "codex"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["sandbox_id"]
        assert data["status"] == "ready"

        g = client.get("/api/tasks/sb-own/sandbox", headers={"Authorization": f"Bearer {jwt}"})
        assert g.status_code == 200
        sb = g.json()["sandbox"]
        assert sb["provider"] == "codex"
        assert sb["task_id"] == "sb-own"
        assert sb["daytona_sandbox_id"] == "daytona-test-123"

    def test_sandbox_create_idempotent(self, client, monkeypatch):
        mock_create = _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-idem")
        r1 = client.post(
            "/api/tasks/sb-idem/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "ready"
        # Second call should return existing sandbox without re-provisioning.
        call_count = mock_create.call_count
        r2 = client.post(
            "/api/tasks/sb-idem/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "ready"
        assert r2.json()["sandbox_id"] == r1.json()["sandbox_id"]
        assert mock_create.call_count == call_count  # no new Daytona call

    def test_sandbox_stop_and_resume(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-stop")
        client.post(
            "/api/tasks/sb-stop/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r = client.post("/api/tasks/sb-stop/sandbox/stop", headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200
        assert r.json()["status"] == "stopped"

        g = client.get("/api/tasks/sb-stop/sandbox", headers={"Authorization": f"Bearer {jwt}"})
        assert g.json()["sandbox"]["status"] == "stopped"

        # Resume: re-provisions a new Daytona sandbox
        r2 = client.post(
            "/api/tasks/sb-stop/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "ready"

    def test_sandbox_delete(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-del")
        client.post(
            "/api/tasks/sb-del/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r = client.delete("/api/tasks/sb-del/sandbox", headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200
        assert r.json()["status"] == "deleted"
        g = client.get("/api/tasks/sb-del/sandbox", headers={"Authorization": f"Bearer {jwt}"})
        assert g.json()["sandbox"] is None

    def test_sandbox_no_daytona_key(self, client):
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-nokey")
        r = client.post(
            "/api/tasks/sb-nokey/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 503

    def test_session_requires_provider_connection(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-noconn")
        client.post(
            "/api/tasks/sb-noconn/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r = client.post(
            "/api/tasks/sb-noconn/sandbox/sessions",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 400
        assert "not connected" in r.json()["detail"]

    def test_session_create_after_sandbox_row(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _connect_provider(uid)
        _seed_private_task(client, uid, task_id="sb-sess")
        client.post(
            "/api/tasks/sb-sess/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r = client.post(
            "/api/tasks/sb-sess/sandbox/sessions",
            json={"provider": "claude_code", "approval_mode": "auto_accept"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        j = r.json()
        assert j["approval_mode"] == "auto_accept"
        assert "--dangerously-skip-permissions" in j["cli_extra_args"]

    def test_session_message_and_events(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _connect_provider(uid)
        _seed_private_task(client, uid, task_id="sb-msg")
        client.post(
            "/api/tasks/sb-msg/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        sr = client.post(
            "/api/tasks/sb-msg/sandbox/sessions",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        sid = sr.json()["session_id"]
        # Send a message
        mr = client.post(
            f"/api/tasks/sb-msg/sandbox/sessions/{sid}/messages",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert mr.status_code == 200
        # Fetch events
        er = client.get(
            f"/api/tasks/sb-msg/sandbox/sessions/{sid}/events?offset=0&limit=50",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert er.status_code == 200
        events = er.json()["events"]
        types = [e["type"] for e in events]
        assert "session.started" in types
        assert "message.user" in types
        assert er.json()["next_offset"] == events[-1]["offset"] + 1
        # Transcript
        tr = client.get(
            f"/api/tasks/sb-msg/sandbox/sessions/{sid}/transcript",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert tr.status_code == 200
        assert len(tr.json()["transcript"]) == len(events)

    def test_session_interrupt_and_permissions(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _connect_provider(uid)
        _seed_private_task(client, uid, task_id="sb-perm")
        client.post(
            "/api/tasks/sb-perm/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        sr = client.post(
            "/api/tasks/sb-perm/sandbox/sessions",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        sid = sr.json()["session_id"]
        # Permission
        pr = client.post(
            f"/api/tasks/sb-perm/sandbox/sessions/{sid}/permissions",
            json={"approved": True, "request_id": "req-1"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert pr.status_code == 200
        assert pr.json()["approved"] is True
        # Interrupt
        ir = client.post(
            f"/api/tasks/sb-perm/sandbox/sessions/{sid}/interrupt",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert ir.status_code == 200
        assert ir.json()["status"] == "interrupted"

    def test_sandbox_logs(self, client, monkeypatch):
        _mock_daytona(monkeypatch)
        jwt, uid = _create_user_with_github(client)
        _seed_private_task(client, uid, task_id="sb-log")
        client.post(
            "/api/tasks/sb-log/sandbox",
            json={"provider": "claude_code"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r = client.get(
            "/api/tasks/sb-log/sandbox/logs?page=1&per_page=50",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        assert len(r.json()["chunks"]) > 0

    def test_agent_connections_list(self, client):
        jwt, uid = _create_user_with_github(client)
        r = client.get("/api/users/me/agent-connections", headers={"Authorization": f"Bearer {jwt}"})
        assert r.status_code == 200
        assert r.json()["connections"] == []

    def test_browser_oauth_flow(self, client):
        jwt, uid = _create_user_with_github(client)
        # 1. Begin browser OAuth
        r = client.post(
            "/api/users/me/agent-connections/claude_code/begin",
            json={"auth_mode": "browser_oauth"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "pending"
        assert data["browser_url"] is not None
        state = data["state"]

        # 2. Check status — should be pending
        r = client.get(
            "/api/users/me/agent-connections/claude_code/status",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.json()["status"] == "pending"

        # 3. Open authorize page
        url = data["browser_url"]
        # Extract path from URL
        path = "/api/auth/agent-providers/claude_code/authorize"
        r = client.get(path, params={"state": state})
        assert r.status_code == 200
        assert "Connect Claude Code" in r.text

        # 4. Submit credential via callback
        r = client.post(
            "/api/auth/agent-providers/claude_code/callback",
            data={"state": state, "credential": "sk-ant-browser-test-key"},
        )
        assert r.status_code == 200
        assert "Connected" in r.text

        # 5. Poll status — should be connected
        r = client.get(
            "/api/users/me/agent-connections/claude_code/status",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.json()["status"] == "connected"

        # 6. List shows connection
        r = client.get("/api/users/me/agent-connections", headers={"Authorization": f"Bearer {jwt}"})
        conns = r.json()["connections"]
        assert len(conns) == 1
        assert conns[0]["status"] == "connected"
        assert conns[0]["auth_mode"] == "browser_oauth"

    def test_browser_oauth_expired_state(self, client):
        jwt, uid = _create_user_with_github(client)
        # Insert expired state
        from datetime import timedelta
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO oauth_states (token, mode, expires_at) VALUES (%s, %s, %s)",
                ("expired-state", f"agent_connect:{uid}:claude_code", now() - timedelta(minutes=1)),
            )
        r = client.get("/api/auth/agent-providers/claude_code/authorize", params={"state": "expired-state"})
        assert r.status_code == 400
        assert "expired" in r.text.lower()

    def test_browser_oauth_invalid_state(self, client):
        r = client.get("/api/auth/agent-providers/claude_code/authorize", params={"state": "bogus"})
        assert r.status_code == 400

    def test_agent_connections_add_and_remove(self, client):
        jwt, uid = _create_user_with_github(client)
        # Begin
        r = client.post(
            "/api/users/me/agent-connections/claude_code/begin",
            json={"auth_mode": "api_key"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        # Complete
        r = client.post(
            "/api/users/me/agent-connections/claude_code/complete",
            json={"credential": "sk-ant-test-key"},
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "connected"
        # List
        r = client.get("/api/users/me/agent-connections", headers={"Authorization": f"Bearer {jwt}"})
        conns = r.json()["connections"]
        assert len(conns) == 1
        assert conns[0]["provider"] == "claude_code"
        assert conns[0]["status"] == "connected"
        # Remove
        r = client.delete(
            "/api/users/me/agent-connections/claude_code",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert r.status_code == 200
        r = client.get("/api/users/me/agent-connections", headers={"Authorization": f"Bearer {jwt}"})
        assert r.json()["connections"] == []
