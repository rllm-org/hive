"""Tests for sandbox WebSocket terminal proxy and session REST."""

import json
import socket
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import WebSocketDisconnect

from hive.server.db import get_db_sync
from tests.server.test_sandbox import _auth, _create_user, _patch_daytona, _seed_task


class TestSandboxTerminalSessions:
    def test_sessions_require_sandbox(self, client, monkeypatch):
        token, _ = _create_user(client)
        _seed_task()
        _patch_daytona(monkeypatch)
        resp = client.get("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token))
        assert resp.status_code == 404

        resp = client.post("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token), json={})
        assert resp.status_code == 404

    def test_sessions_crud_and_isolation(self, client, monkeypatch):
        token_a, _ = _create_user(client, "term-a@test.com")
        token_b, _ = _create_user(client, "term-b@test.com")
        _seed_task()
        _patch_daytona(monkeypatch)

        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token_a))

        r = client.post(
            "/api/tasks/hive/sandbox-task/sandbox/sessions",
            headers=_auth(token_a),
            json={"title": "shell 1"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["id"] >= 1
        assert body["ticket"]
        assert body["title"] == "shell 1"

        r = client.get("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token_a))
        assert r.status_code == 200
        sessions = r.json()["sessions"]
        assert len(sessions) == 1
        assert sessions[0]["title"] == "shell 1"
        sid = sessions[0]["id"]

        r = client.delete(f"/api/tasks/hive/sandbox-task/sandbox/sessions/{sid}", headers=_auth(token_b))
        assert r.status_code == 404

        r = client.delete(f"/api/tasks/hive/sandbox-task/sandbox/sessions/{sid}", headers=_auth(token_a))
        assert r.status_code == 200
        assert r.json()["status"] == "closed"

        r = client.get("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token_a))
        assert r.json()["sessions"] == []

    def test_sessions_require_auth(self, client, monkeypatch):
        _seed_task()
        _patch_daytona(monkeypatch)
        assert client.get("/api/tasks/hive/sandbox-task/sandbox/sessions").status_code in (401, 422)
        assert client.post("/api/tasks/hive/sandbox-task/sandbox/sessions", json={}).status_code in (401, 422)

    def test_delete_sandbox_cascades_terminal_sessions(self, client, monkeypatch):
        token, _ = _create_user(client, "term-cascade@test.com")
        _seed_task()
        _patch_daytona(monkeypatch)
        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        r = client.post("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token), json={})
        session_id = r.json()["id"]
        with get_db_sync() as conn:
            row = conn.execute(
                "SELECT sandbox_id FROM sandbox_terminal_sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
            sb_id = row["sandbox_id"]

        client.delete("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))

        with get_db_sync() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS c FROM sandbox_terminal_sessions WHERE sandbox_id = %s",
                (sb_id,),
            ).fetchone()["c"]
        assert n == 0

    def test_ws_rejects_invalid_ticket(self, client, monkeypatch):
        _seed_task()
        _patch_daytona(monkeypatch)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/tasks/hive/sandbox-task/sandbox/terminal/ws?ticket=not-a-valid-ticket"
            ):
                pass

    @patch("hive.server.sandbox_terminal.paramiko.Transport")
    def test_ws_ping_pong(self, mock_transport_cls, client, monkeypatch):
        token, _ = _create_user(client, "term-ws@test.com")
        _seed_task()
        _patch_daytona(monkeypatch)
        client.post("/api/tasks/hive/sandbox-task/sandbox", headers=_auth(token))
        r = client.post("/api/tasks/hive/sandbox-task/sandbox/sessions", headers=_auth(token), json={})
        ticket = r.json()["ticket"]

        transport = MagicMock()
        mock_transport_cls.return_value = transport
        transport.is_active.return_value = True
        chan = MagicMock()
        chan.closed = False
        transport.open_session.return_value = chan
        _recv_i = [0]

        def recv_fn(_n):
            _recv_i[0] += 1
            if _recv_i[0] < 500:
                raise socket.timeout
            return b""

        chan.recv = recv_fn

        with client.websocket_connect(
            f"/api/tasks/hive/sandbox-task/sandbox/terminal/ws?ticket={ticket}"
        ) as ws:
            ws.send_text(json.dumps({"type": "ping"}))
            msg = ws.receive_json()
            assert msg["type"] == "pong"
