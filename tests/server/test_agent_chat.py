"""Tests for the agent-chat proxy in src/hive/server/agent_chat.py.

The real agent-sdk lives out of process. We replace get_client() with a
recording fake so we exercise the routing, auth, DB mapping, and the SSE
byte-level pass-through without a live upstream.
"""

from __future__ import annotations

from typing import Any

import pytest

from hive.server import agent_chat
from hive.server.agent_chat import router as agent_chat_router
from hive.server.db import get_db_sync, now
from hive.server.main import app
from tests.conftest import _create_verified_user


# Make sure the router is registered regardless of HIVE_AGENT_CHAT env
# at import time (the fixture may start before env is set).
if not any(getattr(r, "path", "").endswith("/agent-chat/sessions") for r in app.routes):
    app.include_router(agent_chat_router)


# --- fake upstream ---------------------------------------------------------

class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []
        self.quick_response = {
            "session_id": "sdk-sess-1",
            "agent_id": "sdk-agent-1",
            "sandbox_id": "sdk-box-1",
            "connected": True,
        }
        self.sse_chunks = [
            b"event: message\n",
            b'data: {"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_delta","content":{"type":"text","text":"hi"}}}}\n\n',
            b'data: {"jsonrpc":"2.0","id":"r1","result":{"stopReason":"end_turn"}}\n\n',
        ]
        self.destroyed: list[str] = []

    async def create_quick_session(self, **cfg):
        self.calls.append(("create_quick_session", (), cfg))
        return dict(self.quick_response)

    async def get_status(self, sid):
        self.calls.append(("get_status", (sid,), {}))
        return {"session_id": sid, "agent_busy": False}

    async def get_log(self, sid, limit=500):
        self.calls.append(("get_log", (sid, limit), {}))
        return []

    async def send_message(self, sid, text, interrupt=False):
        self.calls.append(("send_message", (sid, text), {"interrupt": interrupt}))
        return {"rpc_id": "r1", "status": "ok"}

    async def cancel(self, sid):
        self.calls.append(("cancel", (sid,), {}))
        return {"status": "ok"}

    async def resume(self, sid):
        self.calls.append(("resume", (sid,), {}))
        return {"status": "resumed"}

    async def set_config(self, sid, **kwargs):
        self.calls.append(("set_config", (sid,), kwargs))
        return {"status": "ok"}

    async def destroy_sandbox(self, sandbox_id):
        self.calls.append(("destroy_sandbox", (sandbox_id,), {}))
        self.destroyed.append(sandbox_id)

    async def stream_events(self, sid):
        self.calls.append(("stream_events", (sid,), {}))
        for chunk in self.sse_chunks:
            yield chunk


@pytest.fixture()
def fake_sdk(monkeypatch):
    fc = FakeClient()
    monkeypatch.setattr(agent_chat, "get_client", lambda: fc)
    return fc


# --- helpers ---------------------------------------------------------------

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_task(owner="hive-mock-dev", slug="smoke", owner_id=None):
    with get_db_sync() as conn:
        row = conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url,"
            " task_type, owner_id, visibility, created_at)"
            " VALUES (%s,%s,%s,%s,%s,'public',%s,'public',%s) RETURNING id",
            (slug, owner, "Test", "t", "https://example.com/x", owner_id, now()),
        ).fetchone()
        return row["id"]


# --- tests -----------------------------------------------------------------

def test_create_forwards_config_and_inserts_row(client, fake_sdk):
    token, _ = _create_verified_user(client, "a@example.com", "pw123456", handle="alice")
    _seed_task(slug="t1")

    r = client.post(
        "/api/tasks/hive-mock-dev/t1/agent-chat/sessions",
        headers=_auth(token),
        json={"agent_kind": "claude", "model": "claude-sonnet-4-6"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sdk_session_id"] == "sdk-sess-1"
    assert body["sdk_sandbox_id"] == "sdk-box-1"
    assert body["status"] == "active"

    # Upstream call was made with the chosen model + defaults
    quick = [c for c in fake_sdk.calls if c[0] == "create_quick_session"]
    assert len(quick) == 1
    cfg = quick[0][2]
    assert cfg["agent_type"] == "claude"
    assert cfg["model"] == "claude-sonnet-4-6"

    # Row persisted + owned by this user
    with get_db_sync() as conn:
        row = conn.execute("SELECT * FROM agent_chat_sessions WHERE id = %s", (body["id"],)).fetchone()
    assert row is not None
    assert row["sdk_session_id"] == "sdk-sess-1"


def test_message_forwards_interrupt_flag(client, fake_sdk):
    token, _ = _create_verified_user(client, "b@example.com", "pw123456", handle="bob")
    _seed_task(slug="t2")
    sid = client.post(
        "/api/tasks/hive-mock-dev/t2/agent-chat/sessions",
        headers=_auth(token), json={},
    ).json()["id"]

    r = client.post(
        f"/api/agent-chat/sessions/{sid}/message",
        headers=_auth(token),
        json={"text": "analyze this", "interrupt": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rpc_id"] == "r1"

    msgs = [c for c in fake_sdk.calls if c[0] == "send_message"]
    assert msgs == [("send_message", ("sdk-sess-1", "analyze this"), {"interrupt": True})]


def test_foreign_session_is_404(client, fake_sdk):
    t_a, _ = _create_verified_user(client, "ua@example.com", "pw123456", handle="useralpha")
    t_b, _ = _create_verified_user(client, "ub@example.com", "pw123456", handle="userbeta")
    _seed_task(slug="t3")
    sid = client.post(
        "/api/tasks/hive-mock-dev/t3/agent-chat/sessions",
        headers=_auth(t_a), json={},
    ).json()["id"]

    r = client.get(f"/api/agent-chat/sessions/{sid}", headers=_auth(t_b))
    assert r.status_code == 404

    r = client.post(
        f"/api/agent-chat/sessions/{sid}/message",
        headers=_auth(t_b),
        json={"text": "hi"},
    )
    assert r.status_code == 404


def test_delete_marks_closed_and_destroys_sandbox(client, fake_sdk):
    token, _ = _create_verified_user(client, "c@example.com", "pw123456", handle="carol")
    _seed_task(slug="t4")
    sid = client.post(
        "/api/tasks/hive-mock-dev/t4/agent-chat/sessions",
        headers=_auth(token), json={},
    ).json()["id"]

    r = client.delete(f"/api/agent-chat/sessions/{sid}", headers=_auth(token))
    assert r.status_code == 204
    assert fake_sdk.destroyed == ["sdk-box-1"]

    with get_db_sync() as conn:
        row = conn.execute(
            "SELECT status, closed_at FROM agent_chat_sessions WHERE id = %s", (sid,),
        ).fetchone()
    assert row["status"] == "closed"
    assert row["closed_at"] is not None


def test_sse_pass_through(client, fake_sdk):
    token, _ = _create_verified_user(client, "d@example.com", "pw123456", handle="dan")
    _seed_task(slug="t5")
    sid = client.post(
        "/api/tasks/hive-mock-dev/t5/agent-chat/sessions",
        headers=_auth(token), json={},
    ).json()["id"]

    with client.stream("GET", f"/api/agent-chat/sessions/{sid}/events", headers=_auth(token)) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = b"".join(resp.iter_bytes())

    # All three upstream chunks should be present verbatim.
    for chunk in fake_sdk.sse_chunks:
        assert chunk in body
