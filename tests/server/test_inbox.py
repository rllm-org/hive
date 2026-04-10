import psycopg
import hive.server.db as _db


def _post_task(slug="t1", owner="hive"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, %s, 0)",
            (slug, owner, slug, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    resp = client.post("/api/register", json=body)
    return resp.json()["token"]


def _post_msg(client, token, channel="general", text="hello", thread_ts=None):
    body = {"text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts
    resp = client.post(
        f"/api/tasks/hive/t1/channels/{channel}/messages",
        json=body,
        params={"token": token},
    )
    return resp.json()


class TestInboxBasic:
    def test_empty_inbox(self, client):
        """New agent with no mentions gets empty inbox."""
        _post_task()
        token = _register(client, "agent-a")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["mentions"] == []
        assert data["unread_count"] == 0

    def test_mention_appears_in_inbox(self, client):
        """Message mentioning agent shows up in their inbox."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        _post_msg(client, token_a, text="hey @agent-b check this")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["mentions"]) == 1
        assert data["unread_count"] == 1
        assert "@agent-b" in data["mentions"][0]["text"]
        assert data["mentions"][0]["channel"] == "general"

    def test_no_cross_agent_leakage(self, client):
        """Agent only sees mentions of itself, not other agents."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        _register(client, "agent-c")
        _post_msg(client, token_a, text="hey @agent-c do something")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b})
        assert resp.json()["mentions"] == []

    def test_thread_reply_mention(self, client):
        """Mention in a thread reply appears in inbox with thread_ts."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        parent = _post_msg(client, token_a, text="parent message")
        _post_msg(client, token_b, text="hey @agent-a look", thread_ts=parent["ts"])
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_a})
        data = resp.json()
        assert len(data["mentions"]) == 1
        assert data["mentions"][0]["thread_ts"] == parent["ts"]

    def test_multiple_channels(self, client):
        """Mentions from different channels all appear in inbox."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        # Create second channel
        client.post("/api/tasks/hive/t1/channels", json={"name": "dev"}, params={"token": token_a})
        _post_msg(client, token_a, channel="general", text="@agent-b in general")
        _post_msg(client, token_a, channel="dev", text="@agent-b in dev")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b})
        data = resp.json()
        assert len(data["mentions"]) == 2
        channels = {m["channel"] for m in data["mentions"]}
        assert channels == {"general", "dev"}


class TestInboxReadUnread:
    def test_mark_read_advances_cursor(self, client):
        """After marking read, mentions move from unread to read."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        _post_msg(client, token_a, text="@agent-b first")
        msg2 = _post_msg(client, token_a, text="@agent-b second")
        # Mark read up to second message
        resp = client.post(
            "/api/tasks/hive/t1/inbox/read",
            json={"ts": msg2["ts"]},
            params={"token": token_b},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        # Unread should be empty now
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "unread"})
        assert resp.json()["unread_count"] == 0
        assert resp.json()["mentions"] == []
        # Read should have both
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "read"})
        assert len(resp.json()["mentions"]) == 2

    def test_partial_read(self, client):
        """Mark only first message read; second stays unread."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        msg1 = _post_msg(client, token_a, text="@agent-b first")
        _post_msg(client, token_a, text="@agent-b second")
        client.post("/api/tasks/hive/t1/inbox/read", json={"ts": msg1["ts"]}, params={"token": token_b})
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "unread"})
        assert len(resp.json()["mentions"]) == 1
        assert resp.json()["unread_count"] == 1
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "read"})
        assert len(resp.json()["mentions"]) == 1

    def test_status_all(self, client):
        """status=all returns both read and unread."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        msg1 = _post_msg(client, token_a, text="@agent-b first")
        _post_msg(client, token_a, text="@agent-b second")
        client.post("/api/tasks/hive/t1/inbox/read", json={"ts": msg1["ts"]}, params={"token": token_b})
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "all"})
        assert len(resp.json()["mentions"]) == 2

    def test_cursor_only_moves_forward(self, client):
        """GREATEST prevents cursor from moving backwards."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        msg1 = _post_msg(client, token_a, text="@agent-b first")
        msg2 = _post_msg(client, token_a, text="@agent-b second")
        # Mark read up to msg2
        client.post("/api/tasks/hive/t1/inbox/read", json={"ts": msg2["ts"]}, params={"token": token_b})
        # Try to move cursor backwards to msg1
        client.post("/api/tasks/hive/t1/inbox/read", json={"ts": msg1["ts"]}, params={"token": token_b})
        # Should still have both as read (cursor didn't go back)
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "status": "unread"})
        assert resp.json()["unread_count"] == 0


class TestInboxPagination:
    def test_limit(self, client):
        """Limit controls how many mentions are returned."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        for i in range(5):
            _post_msg(client, token_a, text=f"@agent-b msg {i}")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "limit": 3})
        data = resp.json()
        assert len(data["mentions"]) == 3
        assert data["has_more"] is True
        assert data["unread_count"] == 5

    def test_before_cursor(self, client):
        """before param fetches older mentions."""
        _post_task()
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        for i in range(5):
            _post_msg(client, token_a, text=f"@agent-b msg {i}")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "limit": 3})
        oldest_ts = resp.json()["mentions"][-1]["ts"]
        resp2 = client.get("/api/tasks/hive/t1/inbox", params={"token": token_b, "limit": 3, "before": oldest_ts})
        assert len(resp2.json()["mentions"]) == 2


class TestInboxAuth:
    def test_no_auth_401(self, client):
        _post_task()
        resp = client.get("/api/tasks/hive/t1/inbox")
        assert resp.status_code == 401

    def test_user_auth_403(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        resp = client.get(
            "/api/tasks/hive/t1/inbox",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 403

    def test_mark_read_no_auth_401(self, client):
        _post_task()
        resp = client.post("/api/tasks/hive/t1/inbox/read", json={"ts": "0"})
        assert resp.status_code == 401

    def test_mark_read_missing_ts_400(self, client):
        _post_task()
        token = _register(client, "agent-a")
        resp = client.post("/api/tasks/hive/t1/inbox/read", json={}, params={"token": token})
        assert resp.status_code == 400

    def test_invalid_status_400(self, client):
        _post_task()
        token = _register(client, "agent-a")
        resp = client.get("/api/tasks/hive/t1/inbox", params={"token": token, "status": "bogus"})
        assert resp.status_code == 400
