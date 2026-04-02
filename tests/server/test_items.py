import psycopg
from datetime import datetime, timedelta, timezone

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
                "status": "in_progress",
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
        assert data["status"] == "in_progress"
        assert data["priority"] == "high"
        assert data["labels"] == ["bug", "urgent-fix"]
        assert data["assignee_id"] == "agent-a"
        assert data["assigned_at"] is not None

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
        client.post("/api/tasks/gsm8k/items", json={"title": "In progress item", "status": "in_progress"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Archived item", "status": "archived"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"status": "in_progress"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "in_progress"

    def test_filter_status_negation(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Review item", "status": "review"}, params={"token": token})
        client.post("/api/tasks/gsm8k/items", json={"title": "Archived item", "status": "archived"}, params={"token": token})
        resp = client.get("/api/tasks/gsm8k/items", params={"status": "!archived"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["status"] == "review"

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
            json={"status": "archived"},
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

    def test_assign_archived_item_409(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post(
            "/api/tasks/gsm8k/items",
            json={"title": "Item", "status": "archived"},
            params={"token": token},
        )
        resp = client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token})
        assert resp.status_code == 409

    def test_expired_assignment_disappears_from_assignee_filter(self, client, monkeypatch):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        assigned_at = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("hive.server.items.now", lambda: assigned_at)
        client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token})

        expired_at = assigned_at + timedelta(hours=3)
        monkeypatch.setattr("hive.server.items.now", lambda: expired_at)
        resp = client.get("/api/tasks/gsm8k/items", params={"assignee": "agent-a"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []

        unassigned = client.get("/api/tasks/gsm8k/items", params={"assignee": "none"})
        assert unassigned.status_code == 200
        assert unassigned.json()["items"][0]["assignee_id"] is None

    def test_expired_assignment_can_be_taken_over(self, client, monkeypatch):
        _post_task(client)
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token_a})
        assigned_at = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("hive.server.items.now", lambda: assigned_at)
        client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token_a})

        expired_at = assigned_at + timedelta(hours=3)
        monkeypatch.setattr("hive.server.items.now", lambda: expired_at)
        resp = client.post("/api/tasks/gsm8k/items/GSM8K-1/assign", params={"token": token_b})
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] == "agent-b"


class TestComments:
    def test_create_comment(self, client):
        _post_task(client)
        token = _register(client, "agent-a")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "Hello"},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "Hello"
        assert data["agent_id"] == "agent-a"
        assert data["item_id"] == "GSM8K-1"

    def test_create_comment_missing_content(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_comment_content_too_long(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "x" * 5001},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_list_comments(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "First"},
            params={"token": token},
        )
        client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "Second"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-1/comments")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["comments"]) == 2
        assert data["comments"][0]["content"] == "First"
        assert data["comments"][1]["content"] == "Second"
        assert data["has_next"] is False

    def test_comment_pagination(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        for i in range(3):
            client.post(
                "/api/tasks/gsm8k/items/GSM8K-1/comments",
                json={"content": f"Comment {i}"},
                params={"token": token},
            )
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-1/comments", params={"page": 1, "per_page": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["comments"]) == 2
        assert data["has_next"] is True

    def test_delete_comment(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        create_resp = client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "To delete"},
            params={"token": token},
        )
        comment_id = create_resp.json()["id"]
        resp = client.delete(
            f"/api/tasks/gsm8k/items/GSM8K-1/comments/{comment_id}",
            params={"token": token},
        )
        assert resp.status_code == 204
        list_resp = client.get("/api/tasks/gsm8k/items/GSM8K-1/comments")
        assert list_resp.json()["comments"] == []

    def test_delete_comment_not_found(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        resp = client.delete(
            "/api/tasks/gsm8k/items/GSM8K-1/comments/9999",
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_delete_comment_only_author(self, client):
        _post_task(client)
        token_a = _register(client, "agent-a")
        token_b = _register(client, "agent-b")
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token_a})
        create_resp = client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "By A"},
            params={"token": token_a},
        )
        comment_id = create_resp.json()["id"]
        resp = client.delete(
            f"/api/tasks/gsm8k/items/GSM8K-1/comments/{comment_id}",
            params={"token": token_b},
        )
        assert resp.status_code == 403

    def test_comment_count_in_item(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/gsm8k/items", json={"title": "Item"}, params={"token": token})
        client.post(
            "/api/tasks/gsm8k/items/GSM8K-1/comments",
            json={"content": "A comment"},
            params={"token": token},
        )
        resp = client.get("/api/tasks/gsm8k/items/GSM8K-1")
        assert resp.json()["comment_count"] == 1
