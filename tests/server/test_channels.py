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


class TestDefaultChannels:
    def test_list_creates_default_channel(self, client):
        _post_task()
        token = _register(client)
        resp = client.get("/api/tasks/hive/t1/channels", params={"token": token})
        assert resp.status_code == 200
        chs = resp.json()["channels"]
        assert [c["name"] for c in chs] == ["general"]
        assert chs[0]["is_default"] is True

    def test_default_channel_idempotent(self, client):
        _post_task()
        token = _register(client)
        client.get("/api/tasks/hive/t1/channels", params={"token": token})
        resp = client.get("/api/tasks/hive/t1/channels", params={"token": token})
        assert resp.status_code == 200
        assert len(resp.json()["channels"]) == 1

    def test_unknown_task_404(self, client):
        token = _register(client)
        resp = client.get("/api/tasks/hive/nope/channels", params={"token": token})
        assert resp.status_code == 404

    def test_read_no_auth_ok(self, client):
        _post_task()
        resp = client.get("/api/tasks/hive/t1/channels")
        assert resp.status_code == 200

    def test_create_no_auth_401(self, client):
        _post_task()
        resp = client.post("/api/tasks/hive/t1/channels", json={"name": "x"})
        assert resp.status_code == 401


class TestCreateChannel:
    def test_create(self, client):
        _post_task()
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/t1/channels",
            json={"name": "ideas"},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "ideas"
        assert data["is_default"] is False

    def test_create_invalid_name(self, client):
        _post_task()
        token = _register(client)
        for bad in ["Bad", "with space", "-leading", "way-too-long-channel-name-here", "", "hi!"]:
            resp = client.post(
                "/api/tasks/hive/t1/channels",
                json={"name": bad},
                params={"token": token},
            )
            assert resp.status_code == 400, f"expected 400 for {bad!r}"

    def test_create_duplicate_409(self, client):
        _post_task()
        token = _register(client)
        client.post("/api/tasks/hive/t1/channels", json={"name": "ideas"}, params={"token": token})
        resp = client.post("/api/tasks/hive/t1/channels", json={"name": "ideas"}, params={"token": token})
        assert resp.status_code == 409

    def test_cannot_create_default_channel_again(self, client):
        _post_task()
        token = _register(client)
        client.get("/api/tasks/hive/t1/channels", params={"token": token})
        resp = client.post("/api/tasks/hive/t1/channels", json={"name": "general"}, params={"token": token})
        assert resp.status_code == 409


class TestPostMessage:
    def test_post_to_general(self, client):
        _post_task()
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "hello world"},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["text"] == "hello world"
        assert data["thread_ts"] is None
        assert data["ts"]

    def test_post_blank_text_400(self, client):
        _post_task()
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "   "},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_post_unknown_channel_404(self, client):
        _post_task()
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/t1/channels/nope/messages",
            json={"text": "hi"},
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_post_thread_reply(self, client):
        _post_task()
        token = _register(client)
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent"},
            params={"token": token},
        ).json()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["thread_ts"] == parent["ts"]

    def test_post_reply_to_unknown_parent_404(self, client):
        _post_task()
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply", "thread_ts": "9999999999.000000"},
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_cannot_reply_to_reply(self, client):
        _post_task()
        token = _register(client)
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent"},
            params={"token": token},
        ).json()
        reply = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply", "thread_ts": parent["ts"]},
            params={"token": token},
        ).json()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "nested", "thread_ts": reply["ts"]},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestHistoryAndThreads:
    def test_history_excludes_thread_replies(self, client):
        _post_task()
        token = _register(client)
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent"},
            params={"token": token},
        ).json()
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply 1", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply 2", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "another top-level"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/hive/t1/channels/general/messages", params={"token": token})
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        texts = [m["text"] for m in msgs]
        assert "parent" in texts
        assert "another top-level" in texts
        assert "reply 1" not in texts
        assert "reply 2" not in texts
        # parent should report reply_count = 2
        parent_in_history = next(m for m in msgs if m["text"] == "parent")
        assert parent_in_history["reply_count"] == 2

    def test_replies_endpoint(self, client):
        _post_task()
        token = _register(client)
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent"},
            params={"token": token},
        ).json()
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply 1", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "reply 2", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        resp = client.get(
            f"/api/tasks/hive/t1/channels/general/messages/{parent['ts']}/replies",
            params={"token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["parent"]["text"] == "parent"
        assert [r["text"] for r in data["replies"]] == ["reply 1", "reply 2"]

    def test_history_pagination(self, client):
        _post_task()
        token = _register(client)
        for i in range(5):
            client.post(
                "/api/tasks/hive/t1/channels/general/messages",
                json={"text": f"msg {i}"},
                params={"token": token},
            )
        resp = client.get(
            "/api/tasks/hive/t1/channels/general/messages",
            params={"token": token, "limit": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 3
        assert data["has_more"] is True
        oldest_ts = data["messages"][0]["ts"]
        resp2 = client.get(
            "/api/tasks/hive/t1/channels/general/messages",
            params={"token": token, "limit": 3, "before": oldest_ts},
        )
        assert resp2.status_code == 200
        # remaining 2 older messages
        assert len(resp2.json()["messages"]) == 2


class TestUserMessages:
    def test_user_can_post_message(self, auth_user):
        client, jwt_token, user = auth_user
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "hello from a human"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] is None
        assert data["user_id"] == user["id"]
        assert data["author"]["kind"] == "user"
        assert data["author"]["display"] == "testuser"
        assert data["text"] == "hello from a human"

    def test_user_message_appears_in_history(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "human says hi"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        resp = client.get("/api/tasks/hive/t1/channels/general/messages")
        msgs = resp.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["author"]["kind"] == "user"
        assert msgs[0]["author"]["handle"] == "testuser"

    def test_unauth_post_rejected(self, client):
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "anonymous"},
        )
        assert resp.status_code == 401

    def test_invalid_agent_token_rejected(self, client):
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "fake"},
            headers={"X-Agent-Token": "not-a-real-token"},
        )
        assert resp.status_code == 401

    def test_invalid_bearer_rejected(self, client):
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "fake"},
            headers={"Authorization": "Bearer hive_00000000-0000-0000-0000-000000000000"},
        )
        assert resp.status_code == 401

    def test_unauth_create_channel_rejected(self, client):
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels",
            json={"name": "anon-channel"},
        )
        assert resp.status_code == 401

    def test_unauth_edit_rejected(self, client, auth_user):
        a_client, jwt_token, _ = auth_user
        _post_task()
        posted = a_client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "user msg"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        resp = client.patch(
            f"/api/tasks/hive/t1/channels/general/messages/{posted['ts']}",
            json={"text": "hijack"},
        )
        assert resp.status_code == 401

    def test_agent_message_has_agent_author(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "agent says hi"},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == "swift-phoenix"
        assert data["user_id"] is None
        assert data["author"]["kind"] == "agent"
        assert data["author"]["display"] == "swift-phoenix"

    def test_user_can_create_channel(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        resp = client.post(
            "/api/tasks/hive/t1/channels",
            json={"name": "user-made"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "user-made"

    def test_user_reply_in_thread(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        token = _register(client, "swift-phoenix")
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent from agent"},
            params={"token": token},
        ).json()
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "human reply", "thread_ts": parent["ts"]},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["author"]["kind"] == "user"
        assert resp.json()["thread_ts"] == parent["ts"]


class TestEditMessage:
    def test_user_can_edit_own_message(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        posted = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "original"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        resp = client.patch(
            f"/api/tasks/hive/t1/channels/general/messages/{posted['ts']}",
            json={"text": "updated"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "updated"
        assert data["edited_at"] is not None

    def test_agent_can_edit_own_message(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        posted = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "agent message"},
            params={"token": token},
        ).json()
        resp = client.patch(
            f"/api/tasks/hive/t1/channels/general/messages/{posted['ts']}",
            json={"text": "updated agent"},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["text"] == "updated agent"

    def test_cannot_edit_others_message(self, client, auth_user):
        # Use auth_user to create the user/task first
        a_client, jwt_token, _ = auth_user
        _post_task()
        posted = a_client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "user msg"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        token = _register(client, "other-agent")
        resp = client.patch(
            f"/api/tasks/hive/t1/channels/general/messages/{posted['ts']}",
            json={"text": "hijack"},
            params={"token": token},
        )
        assert resp.status_code == 403

    def test_edited_at_in_history(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        posted = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "first"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        ).json()
        client.patch(
            f"/api/tasks/hive/t1/channels/general/messages/{posted['ts']}",
            json={"text": "second"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        resp = client.get("/api/tasks/hive/t1/channels/general/messages")
        msgs = resp.json()["messages"]
        assert msgs[0]["text"] == "second"
        assert msgs[0]["edited_at"] is not None

    def test_edit_unknown_message_404(self, auth_user):
        client, jwt_token, _ = auth_user
        _post_task()
        resp = client.patch(
            "/api/tasks/hive/t1/channels/general/messages/9999999999.000000",
            json={"text": "x"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 404


class TestMentions:
    def test_valid_mention_stored(self, client):
        _post_task()
        token_a = _register(client, "swift-phoenix")
        _register(client, "quiet-atlas")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "hey @quiet-atlas check this"},
            params={"token": token_a},
        )
        assert resp.status_code == 201
        assert resp.json()["mentions"] == ["quiet-atlas"]

    def test_invalid_mention_dropped(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "hey @nonexistent-agent how are you"},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["mentions"] == []

    def test_multiple_mentions_deduped(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        _register(client, "quiet-atlas")
        _register(client, "bold-cipher")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "@quiet-atlas @bold-cipher and @quiet-atlas again"},
            params={"token": token},
        )
        assert resp.status_code == 201
        # Order preserved, duplicates removed
        assert resp.json()["mentions"] == ["quiet-atlas", "bold-cipher"]

    def test_self_mention_allowed(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "note to @swift-phoenix: try again later"},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["mentions"] == ["swift-phoenix"]

    def test_mention_case_insensitive(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        _register(client, "quiet-atlas")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "ping @QUIET-Atlas"},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["mentions"] == ["quiet-atlas"]

    def test_mentions_in_history(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        _register(client, "quiet-atlas")
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "hey @quiet-atlas"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/hive/t1/channels/general/messages")
        assert resp.status_code == 200
        msgs = resp.json()["messages"]
        assert len(msgs) == 1
        assert msgs[0]["mentions"] == ["quiet-atlas"]

    def test_mentions_in_thread_replies(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        _register(client, "quiet-atlas")
        parent = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "parent message"},
            params={"token": token},
        ).json()
        client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "ping @quiet-atlas in reply", "thread_ts": parent["ts"]},
            params={"token": token},
        )
        resp = client.get(
            f"/api/tasks/hive/t1/channels/general/messages/{parent['ts']}/replies",
        )
        replies = resp.json()["replies"]
        assert len(replies) == 1
        assert replies[0]["mentions"] == ["quiet-atlas"]

    def test_no_at_no_mentions(self, client):
        _post_task()
        token = _register(client, "swift-phoenix")
        resp = client.post(
            "/api/tasks/hive/t1/channels/general/messages",
            json={"text": "plain message no mentions"},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["mentions"] == []


