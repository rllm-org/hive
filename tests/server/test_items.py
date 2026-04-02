import psycopg

import hive.server.db as _db


def _post_task(client, task_id="gsm8k"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    resp = client.post("/api/register", json=body)
    return resp.json()["token"]


class TestCreateItem:
    def test_minimal_create(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post("/api/tasks/gsm8k/items", json={"title": "First item"}, params={"token": token})
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "GSM8K-1"
        assert data["status"] == "backlog"
        assert data["priority"] == "none"
        assert data["comment_count"] == 0
        assert data["labels"] == []

    def test_create_with_all_fields(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        resp = client.post(
            "/api/tasks/gsm8k/items",
            json={
                "title": "Full item",
                "description": "desc",
                "status": "todo",
                "priority": "high",
                "labels": ["bug", "urgent-fix"],
                "assignee_id": "agent-a",
            },
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Full item"
        assert data["description"] == "desc"
        assert data["status"] == "todo"
        assert data["priority"] == "high"
        assert data["labels"] == ["bug", "urgent-fix"]
        assert data["assignee_id"] == "agent-a"

    def test_id_increments(self, client):
        _post_task(client)
        token = _register(client)
        r1 = client.post("/api/tasks/gsm8k/items", json={"title": "Item 1"}, params={"token": token})
        r2 = client.post("/api/tasks/gsm8k/items", json={"title": "Item 2"}, params={"token": token})
        assert r1.json()["id"] == "GSM8K-1"
        assert r2.json()["id"] == "GSM8K-2"

    def test_invalid_status(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Bad status", "status": "invalid"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_invalid_label_chars(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Bad label", "labels": ["bad label!"]},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_no_auth(self, client):
        _post_task(client)
        resp = client.post("/api/tasks/gsm8k/items", json={"title": "No auth"})
        assert resp.status_code == 422

    def test_task_not_found(self, client):
        token = _register(client)
        resp = client.post(
            "/api/tasks/nonexistent/items",
            json={"title": "Orphan"},
            params={"token": token},
        )
        assert resp.status_code == 404


class TestGetItem:
    def test_get_by_id(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "My item"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "GSM8K-1"
        assert data["children"] == []

    def test_get_with_children(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Parent"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Child", "parent_id": "GSM8K-1"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["children"]) == 1
        assert data["children"][0]["id"] == "GSM8K-2"
        assert data["children"][0]["title"] == "Child"

    def test_not_found(self, client):
        _post_task(client)
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-999")
        assert resp.status_code == 404
