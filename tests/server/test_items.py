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


class TestListItems:
    def test_list_empty(self, client):
        _post_task(client)
        resp = client.get("/api/tasks/gsm8k/items")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_next"] is False

    def test_list_returns_items(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item A"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Item B"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    def test_filter_by_status(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Todo item", "status": "todo"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Done item", "status": "done"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"status": "todo"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "todo"

    def test_filter_status_negation(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Todo item", "status": "todo"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Done item", "status": "done"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"status": "!done"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "todo"

    def test_filter_assignee_none(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post("/api/tasks/gsm8k/items", json={"title": "Unassigned"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Assigned", "assignee_id": "agent-a"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/gsm8k/items", params={"assignee": "none"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["assignee_id"] is None

    def test_filter_by_label(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Bug item", "labels": ["bug"]}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Feature item", "labels": ["feature"]}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"label": "bug"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert "bug" in data["items"][0]["labels"]

    def test_filter_by_parent(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Parent"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Child", "parent_id": "GSM8K-1"},
            params={"token": token},
        )
        client.post("/api/tasks/gsm8k/items", json={"title": "Unrelated"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"parent": "GSM8K-1"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "GSM8K-2"

    def test_sort_by_priority(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Low item", "priority": "low"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Urgent item", "priority": "urgent"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"sort": "priority"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["priority"] == "urgent"

    def test_pagination(self, client):
        _post_task(client)
        token = _register(client)
        for i in range(3):
            client.post("/api/tasks/gsm8k/items", json={"title": f"Item {i}"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"page": 1, "per_page": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_next"] is True


class TestPatchItem:
    def test_update_status(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-1",
            json={"status": "in_progress"},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

    def test_update_multiple_fields(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-1",
            json={"title": "Updated", "priority": "high", "labels": ["bug"]},
            params={"token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated"
        assert data["priority"] == "high"
        assert data["labels"] == ["bug"]

    def test_update_invalid_status(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-1",
            json={"status": "invalid"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_cycle_detection(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "A"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "B", "parent_id": "GSM8K-1"},
            params={"token": token},
        )
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-1",
            json={"parent_id": "GSM8K-2"},
            params={"token": token},
        )
        assert resp.status_code == 400
        assert "cycle" in resp.json()["detail"]

    def test_self_parent_rejected(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "A"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-1",
            json={"parent_id": "GSM8K-1"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_max_depth_exceeded(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "1"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "2", "parent_id": "GSM8K-1"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "3", "parent_id": "GSM8K-2"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "4", "parent_id": "GSM8K-3"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "5", "parent_id": "GSM8K-4"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "6"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-6",
            json={"parent_id": "GSM8K-5"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_not_found(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.patch(
            "/api/tasks/gsm8k/items/GSM8K-999",
            json={"status": "done"},
            params={"token": token},
        )
        assert resp.status_code == 404


class TestDeleteItem:
    def test_delete(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.delete("/api/tasks/gsm8k/items/GSM8K-1", params={"token": token})
        assert resp.status_code == 204
        list_resp = client.get("/api/tasks/gsm8k/items")
        assert list_resp.json()["items"] == []

    def test_delete_only_creator(self, client):
        _post_task(client)
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token_a})
        resp = client.delete("/api/tasks/gsm8k/items/GSM8K-1", params={"token": token_b})
        assert resp.status_code == 403

    def test_delete_with_children_409(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Parent"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Child", "parent_id": "GSM8K-1"}, params={"token": token})
        resp = client.delete("/api/tasks/gsm8k/items/GSM8K-1", params={"token": token})
        assert resp.status_code == 409

    def test_delete_not_found(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.delete("/api/tasks/gsm8k/items/GSM8K-999", params={"token": token})
        assert resp.status_code == 404


class TestBulkCreate:
    def test_bulk_create(self, client):
        _post_task(client, "gsm8k")
        token = _register(client)
        resp = client.post(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"title": "A"}, {"title": "B"}, {"title": "C"}]},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["items"][0]["id"] == "GSM8K-1"
        assert data["items"][1]["id"] == "GSM8K-2"
        assert data["items"][2]["id"] == "GSM8K-3"

    def test_bulk_create_validation_rejects_all(self, client):
        _post_task(client, "gsm8k")
        token = _register(client)
        resp = client.post(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"title": "Good"}, {"title": "Bad", "status": "invalid"}]},
            params={"token": token},
        )
        assert resp.status_code == 400
        list_resp = client.get("/api/tasks/gsm8k/items")
        assert list_resp.json()["items"] == []

    def test_bulk_create_max_50(self, client):
        _post_task(client, "gsm8k")
        token = _register(client)
        resp = client.post(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"title": f"Item {i}"} for i in range(51)]},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestBulkUpdate:
    def test_bulk_update(self, client):
        _post_task(client, "gsm8k")
        token = _register(client)
        client.post(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"title": "A"}, {"title": "B"}]},
            params={"token": token},
        )
        resp = client.patch(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"id": "GSM8K-1", "status": "done"}, {"id": "GSM8K-2", "status": "in_progress"}]},
            params={"token": token},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["items"][0]["status"] == "done"
        assert data["items"][1]["status"] == "in_progress"

    def test_bulk_update_max_50(self, client):
        _post_task(client, "gsm8k")
        token = _register(client)
        resp = client.patch(
            "/api/tasks/gsm8k/items/bulk",
            json={"items": [{"id": f"GSM8K-{i}", "status": "done"} for i in range(51)]},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestAssignItem:
    def test_assign_unassigned(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token})
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] == "agent-a"

    def test_assign_already_assigned_409(self, client):
        _post_task(client)
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token_a})
        client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token_a})
        resp = client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token_b})
        assert resp.status_code == 409

    def test_assign_self_already_assigned_ok(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token})
        resp = client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token})
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] == "agent-a"
