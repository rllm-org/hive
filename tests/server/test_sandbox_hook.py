"""Tests for sandbox hook (adapter ingestion) endpoints."""

from hive.server.db import get_db_sync, now
from tests.server.test_private_tasks import _create_user_with_github, _seed_private_task


def _setup_sandbox_with_token(client, monkeypatch):
    """Create a sandbox row with an adapter_token directly in DB."""
    jwt, uid = _create_user_with_github(client)
    _seed_private_task(client, uid, task_id="hook-task")
    token = "test-adapter-token-abc123"
    sid = "hook-sandbox-1"
    ts = now()
    with get_db_sync() as conn:
        conn.execute(
            """INSERT INTO task_sandboxes
               (id, task_id, owner_id, provider, status, adapter_token, created_at, last_active_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (sid, "hook-task", uid, "claude_code", "ready", token, ts, ts),
        )
    return jwt, uid, sid, token


def _create_session(conn, sandbox_id, session_id="hook-sess-1"):
    ts = now()
    conn.execute(
        """INSERT INTO agent_sessions
           (id, sandbox_id, title, status, approval_mode, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (session_id, sandbox_id, "test", "running", "guarded", ts, ts),
    )
    return session_id


class TestSandboxHookAuth:
    def test_missing_token_returns_422(self, client):
        r = client.post("/api/sandbox-hook/events", json={"session_id": "x", "events": []})
        assert r.status_code == 422

    def test_invalid_token_returns_401(self, client):
        r = client.post(
            "/api/sandbox-hook/events",
            json={"session_id": "x", "events": []},
            headers={"X-Sandbox-Token": "bogus"},
        )
        assert r.status_code == 401

    def test_stopped_sandbox_rejected(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            conn.execute("UPDATE task_sandboxes SET status = 'stopped' WHERE id = %s", (sid,))
        r = client.post(
            "/api/sandbox-hook/events",
            json={"session_id": "x", "events": []},
            headers={"X-Sandbox-Token": token},
        )
        assert r.status_code == 401


class TestPushEvents:
    def test_push_events_stores_them(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            sess_id = _create_session(conn, sid)
        r = client.post(
            "/api/sandbox-hook/events",
            json={
                "session_id": sess_id,
                "events": [
                    {"type": "message.assistant", "data": {"text": "Hello from Claude"}},
                    {"type": "tool.call.started", "data": {"tool": "Read", "input": {}}},
                ],
            },
            headers={"X-Sandbox-Token": token},
        )
        assert r.status_code == 200
        assert r.json()["inserted"] == 2

        # Verify via events endpoint
        er = client.get(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/events?offset=0&limit=50",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        events = er.json()["events"]
        types = [e["type"] for e in events]
        assert "message.assistant" in types
        assert "tool.call.started" in types

    def test_push_to_nonexistent_session_rejected(self, client, monkeypatch):
        _setup_sandbox_with_token(client, monkeypatch)
        r = client.post(
            "/api/sandbox-hook/events",
            json={"session_id": "nonexistent", "events": [{"type": "x", "data": {}}]},
            headers={"X-Sandbox-Token": "test-adapter-token-abc123"},
        )
        assert r.status_code == 404


class TestPendingMessages:
    def test_polls_user_messages(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            sess_id = _create_session(conn, sid)

        # User sends a message via the normal API
        client.post(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/messages",
            json={"message": "please fix the bug"},
            headers={"Authorization": f"Bearer {jwt}"},
        )

        # Adapter polls for pending messages
        r = client.get(
            "/api/sandbox-hook/pending",
            params={"session_id": sess_id, "after_seq": -1},
            headers={"X-Sandbox-Token": token},
        )
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["data"]["text"] == "please fix the bug"
        assert r.json()["session_status"] == "running"

        # Poll again with updated seq — should get nothing
        r2 = client.get(
            "/api/sandbox-hook/pending",
            params={"session_id": sess_id, "after_seq": msgs[0]["seq"]},
            headers={"X-Sandbox-Token": token},
        )
        assert r2.json()["messages"] == []

    def test_polls_returns_interrupted_status(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            sess_id = _create_session(conn, sid)

        # Interrupt the session
        client.post(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/interrupt",
            headers={"Authorization": f"Bearer {jwt}"},
        )

        r = client.get(
            "/api/sandbox-hook/pending",
            params={"session_id": sess_id, "after_seq": -1},
            headers={"X-Sandbox-Token": token},
        )
        assert r.json()["session_status"] == "interrupted"


class TestSessionUpdate:
    def test_adapter_marks_session_completed(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            sess_id = _create_session(conn, sid)

        r = client.post(
            "/api/sandbox-hook/session-update",
            json={"session_id": sess_id, "status": "completed"},
            headers={"X-Sandbox-Token": token},
        )
        assert r.status_code == 200

        # Verify session status changed
        gr = client.get(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        assert gr.json()["status"] == "completed"


class TestHeartbeat:
    def test_heartbeat_updates_last_active(self, client, monkeypatch):
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        r = client.post("/api/sandbox-hook/heartbeat", headers={"X-Sandbox-Token": token})
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestFullFlow:
    def test_user_message_to_adapter_response(self, client, monkeypatch):
        """End-to-end: user sends message → adapter polls → adapter pushes response."""
        jwt, uid, sid, token = _setup_sandbox_with_token(client, monkeypatch)
        with get_db_sync() as conn:
            sess_id = _create_session(conn, sid)

        # 1. User sends message
        client.post(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/messages",
            json={"message": "what files are in this repo?"},
            headers={"Authorization": f"Bearer {jwt}"},
        )

        # 2. Adapter polls
        r = client.get(
            "/api/sandbox-hook/pending",
            params={"session_id": sess_id, "after_seq": -1},
            headers={"X-Sandbox-Token": token},
        )
        msgs = r.json()["messages"]
        assert len(msgs) == 1
        last_seq = msgs[0]["seq"]

        # 3. Adapter pushes Claude Code output events
        client.post(
            "/api/sandbox-hook/events",
            json={
                "session_id": sess_id,
                "events": [
                    {"type": "message.assistant", "data": {"text": "Let me check the files."}},
                    {"type": "tool.call.started", "data": {"tool": "Bash", "input": {"command": "ls"}}},
                    {"type": "tool.call.finished", "data": {"content": "README.md\nsrc/\ntests/"}},
                    {"type": "message.assistant", "data": {"text": "The repo contains README.md, src/, and tests/."}},
                ],
            },
            headers={"X-Sandbox-Token": token},
        )

        # 4. User can see the full transcript
        tr = client.get(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/transcript",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        transcript = tr.json()["transcript"]
        types = [e["type"] for e in transcript]
        assert "message.user" in types
        assert "message.assistant" in types
        assert "tool.call.started" in types
        assert "tool.call.finished" in types
        assert len(transcript) >= 5  # user msg + 4 adapter events

        # 5. User sends follow-up
        client.post(
            f"/api/tasks/hook-task/sandbox/sessions/{sess_id}/messages",
            json={"message": "show me the README"},
            headers={"Authorization": f"Bearer {jwt}"},
        )

        # 6. Adapter polls with updated seq
        r2 = client.get(
            "/api/sandbox-hook/pending",
            params={"session_id": sess_id, "after_seq": last_seq},
            headers={"X-Sandbox-Token": token},
        )
        msgs2 = r2.json()["messages"]
        assert len(msgs2) == 1
        assert msgs2[0]["data"]["text"] == "show me the README"
