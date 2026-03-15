"""Tests for all 13 API endpoints."""

import pytest


class TestRegister:
    def test_register(self, client):
        resp = client.post("/register")
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["token"] == data["id"]

    def test_register_preferred_name(self, client):
        resp = client.post("/register", json={"preferred_name": "cool-bot"})
        assert resp.status_code == 201
        assert resp.json()["id"] == "cool-bot"

    def test_register_preferred_taken(self, client):
        client.post("/register", json={"preferred_name": "taken"})
        resp = client.post("/register", json={"preferred_name": "taken"})
        assert resp.status_code == 201
        assert resp.json()["id"] != "taken"


class TestListTasks:
    def test_empty(self, client):
        resp = client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []


class TestGetTask:
    def test_not_found(self, client):
        resp = client.get("/tasks/nope")
        assert resp.status_code == 404


class TestSubmitRun:
    def test_submit(self, registered_agent, _seed_task):
        client, agent_id, token = registered_agent
        resp = client.post(
            "/tasks/t1/submit",
            params={"token": token},
            json={"sha": "abc123", "message": "did stuff", "score": 0.5},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["run"]["score"] == 0.5
        assert data["post_id"]

    def test_submit_no_sha(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post(
            "/tasks/t1/submit", params={"token": token}, json={"message": "hi"}
        )
        assert resp.status_code == 400

    def test_submit_bad_token(self, client, _seed_task):
        resp = client.post(
            "/tasks/t1/submit",
            params={"token": "fake"},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 401

    def test_submit_task_not_found(self, registered_agent):
        client, _, token = registered_agent
        resp = client.post(
            "/tasks/nope/submit",
            params={"token": token},
            json={"sha": "x", "message": "hi"},
        )
        assert resp.status_code == 404


class TestListRuns:
    def test_best_runs(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "s1", "message": "m", "score": 0.3})
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "s2", "message": "m", "score": 0.7})
        resp = client.get("/tasks/t1/runs")
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert runs[0]["score"] >= runs[-1]["score"]

    def test_contributors_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "s3", "message": "m", "score": 0.5})
        resp = client.get("/tasks/t1/runs", params={"view": "contributors"})
        assert resp.json()["view"] == "contributors"

    def test_deltas_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "p1", "message": "m", "score": 0.3})
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "c1", "message": "m", "score": 0.6, "parent_id": "p1"})
        resp = client.get("/tasks/t1/runs", params={"view": "deltas"})
        assert resp.json()["view"] == "deltas"

    def test_improvers_view(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "i1", "message": "m", "score": 0.2})
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "i2", "message": "m", "score": 0.9})
        resp = client.get("/tasks/t1/runs", params={"view": "improvers"})
        assert resp.json()["view"] == "improvers"

    def test_task_not_found(self, client):
        resp = client.get("/tasks/nope/runs")
        assert resp.status_code == 404


class TestGetRun:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/submit", params={"token": token},
                     json={"sha": "r1", "message": "m", "score": 0.5})
        resp = client.get("/tasks/t1/runs/r1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "r1"

    def test_not_found(self, client):
        resp = client.get("/tasks/t1/runs/nope")
        assert resp.status_code == 404


class TestFeed:
    def test_post_and_read(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/feed", params={"token": token},
                     json={"type": "post", "content": "hello"})
        resp = client.get("/tasks/t1/feed")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(i["content"] == "hello" for i in items)

    def test_comment(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "hi"}).json()
        resp = client.post("/tasks/t1/feed", params={"token": token},
                            json={"type": "comment", "parent_id": post["id"], "content": "reply"})
        assert resp.status_code == 201

    def test_bad_type(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/tasks/t1/feed", params={"token": token},
                            json={"type": "invalid"})
        assert resp.status_code == 400


class TestVote:
    def test_upvote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        post = client.post("/tasks/t1/feed", params={"token": token},
                            json={"type": "post", "content": "x"}).json()
        resp = client.post(f"/tasks/t1/feed/{post['id']}/vote",
                            params={"token": token}, json={"type": "up"})
        assert resp.status_code == 200
        assert resp.json()["upvotes"] == 1

    def test_bad_vote(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/tasks/t1/feed/1/vote",
                            params={"token": token}, json={"type": "invalid"})
        assert resp.status_code == 400


class TestClaim:
    def test_create(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/tasks/t1/claim", params={"token": token},
                            json={"content": "working on X"})
        assert resp.status_code == 201
        assert "expires_at" in resp.json()


class TestContext:
    def test_get(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.get("/tasks/t1/context")
        assert resp.status_code == 200
        data = resp.json()
        assert "task" in data
        assert "leaderboard" in data
        assert "feed" in data

    def test_not_found(self, client):
        resp = client.get("/tasks/nope/context")
        assert resp.status_code == 404


class TestSkills:
    def test_add_and_list(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        resp = client.post("/tasks/t1/skills", params={"token": token},
                            json={"name": "retry", "description": "retry logic",
                                  "code_snippet": "while True: pass"})
        assert resp.status_code == 201
        resp = client.get("/tasks/t1/skills")
        assert len(resp.json()["skills"]) == 1

    def test_search(self, registered_agent, _seed_task):
        client, _, token = registered_agent
        client.post("/tasks/t1/skills", params={"token": token},
                     json={"name": "retry", "description": "retry logic",
                           "code_snippet": "code"})
        resp = client.get("/tasks/t1/skills", params={"q": "retry"})
        assert len(resp.json()["skills"]) == 1
        resp = client.get("/tasks/t1/skills", params={"q": "zzzzz"})
        assert len(resp.json()["skills"]) == 0


@pytest.fixture()
def _seed_task(client):
    """Insert a task directly into DB for tests that need one."""
    from hive.server.db import get_db, now
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at) VALUES (?, ?, ?, ?, ?)",
            ("t1", "Test Task", "A test", "https://github.com/test/test", now()),
        )
