"""Adversarial stress tests for the Items API."""
import psycopg

import hive.server.db as _db


def _post_task(client, task_id="stress-task"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "stress test", "https://github.com/test", _db.now()),
        )


def _post_task_no_seq(client, task_id="no-seq-task"):
    """Insert a task row WITHOUT item_seq to test the migration path."""
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            (task_id, task_id, "no seq", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    resp = client.post("/api/register", json=body)
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# 1. Boundary conditions
# ---------------------------------------------------------------------------


class TestTitleBoundary:
    def test_title_500_chars_passes(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "x" * 500},
            params={"token": token},
        )
        assert resp.status_code == 201

    def test_title_501_chars_fails(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "x" * 501},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_empty_title_fails(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": ""},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_whitespace_only_title_fails(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "   "},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestDescriptionBoundary:
    def test_description_10000_chars_passes(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "description": "x" * 10000},
            params={"token": token},
        )
        assert resp.status_code == 201

    def test_description_10001_chars_fails(self, client):
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "description": "x" * 10001},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestCommentBoundary:
    def test_comment_5000_chars_passes(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "x" * 5000},
            params={"token": token},
        )
        assert resp.status_code == 201

    def test_comment_5001_chars_fails(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "x" * 5001},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestLabelBoundary:
    def test_20_labels_passes(self, client):
        _post_task(client)
        token = _register(client)
        labels = [f"label-{i}" for i in range(20)]
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "labels": labels},
            params={"token": token},
        )
        assert resp.status_code == 201

    def test_21_labels_fails(self, client):
        _post_task(client)
        token = _register(client)
        labels = [f"label-{i}" for i in range(21)]
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "labels": labels},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_label_50_chars_passes(self, client):
        _post_task(client)
        token = _register(client)
        label = "x" * 50
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "labels": [label]},
            params={"token": token},
        )
        assert resp.status_code == 201

    def test_label_51_chars_fails(self, client):
        _post_task(client)
        token = _register(client)
        label = "x" * 51
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item", "labels": [label]},
            params={"token": token},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_create_item_on_task_without_item_seq(self, client):
        """Task created without item_seq column should still work after migration."""
        _post_task_no_seq(client, "no-seq-task")
        token = _register(client)
        resp = client.post(
            "/api/tasks/no-seq-task/items",
            json={"title": "item on no-seq task"},
            params={"token": token},
        )
        # The item_seq column was added via ALTER TABLE in init_db
        # so this should succeed after migration
        assert resp.status_code == 201

    def test_patch_empty_body_fails(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/stress-task/items/STRESS-1",
            json={},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_no_updatable_fields_fails(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.patch(
            "/api/tasks/stress-task/items/STRESS-1",
            json={"unknown_field": "value", "another_unknown": 123},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_delete_already_soft_deleted_item_404(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})
        resp = client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})
        assert resp.status_code == 404

    def test_get_soft_deleted_item_404(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})
        resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        assert resp.status_code == 404

    def test_assign_same_agent_idempotent(self, client):
        _post_task(client)
        token = _register(client, "same-agent")
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        r1 = client.post("/api/tasks/stress-task/items/STRESS-1/assign", params={"token": token})
        assert r1.status_code == 200
        r2 = client.post("/api/tasks/stress-task/items/STRESS-1/assign", params={"token": token})
        assert r2.status_code == 200
        assert r2.json()["assignee_id"] == "same-agent"

    def test_create_item_with_deleted_parent_fails(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "parent"}, params={"token": token})
        client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "orphan child", "parent_id": "STRESS-1"},
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_filter_multiple_params_combined(self, client):
        _post_task(client)
        token = _register(client, "filter-agent")
        client.post(
            "/api/tasks/stress-task/items",
            json={"title": "Match all", "status": "review", "assignee_id": "filter-agent", "labels": ["bug"]},
            params={"token": token},
        )
        client.post(
            "/api/tasks/stress-task/items",
            json={"title": "Only review", "status": "review"},
            params={"token": token},
        )
        client.post(
            "/api/tasks/stress-task/items",
            json={"title": "Only assigned", "assignee_id": "filter-agent"},
            params={"token": token},
        )
        resp = client.get(
            "/api/tasks/stress-task/items",
            params={"status": "review", "assignee": "filter-agent", "label": "bug"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Match all"

    def test_negation_filter_nonexistent_status(self, client):
        """Negation filter with a non-existent status should be rejected."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item 1", "status": "backlog"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "item 2", "status": "archived"}, params={"token": token})
        resp = client.get("/api/tasks/stress-task/items", params={"status": "!nonexistent"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Authorization
# ---------------------------------------------------------------------------


class TestAuthorization:
    def test_agent_b_cannot_delete_agent_a_item(self, client):
        _post_task(client)
        token_a = _register(client, "auth-agent-a")
        token_b = _register(client, "auth-agent-b")
        client.post("/api/tasks/stress-task/items", json={"title": "A's item"}, params={"token": token_a})
        resp = client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token_b})
        assert resp.status_code == 403

    def test_agent_b_cannot_delete_agent_a_comment(self, client):
        _post_task(client)
        token_a = _register(client, "comment-agent-a")
        token_b = _register(client, "comment-agent-b")
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token_a})
        create_resp = client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "A's comment"},
            params={"token": token_a},
        )
        comment_id = create_resp.json()["id"]
        resp = client.delete(
            f"/api/tasks/stress-task/items/STRESS-1/comments/{comment_id}",
            params={"token": token_b},
        )
        assert resp.status_code == 403

    def test_invalid_token_returns_401(self, client):
        _post_task(client)
        resp = client.post(
            "/api/tasks/stress-task/items",
            json={"title": "item"},
            params={"token": "totally-fake-token-xyz"},
        )
        assert resp.status_code == 401

    def test_missing_token_on_create_returns_422(self, client):
        _post_task(client)
        resp = client.post("/api/tasks/stress-task/items", json={"title": "item"})
        assert resp.status_code == 422

    def test_missing_token_on_patch_returns_422(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.patch("/api/tasks/stress-task/items/STRESS-1", json={"status": "archived"})
        assert resp.status_code == 422

    def test_missing_token_on_delete_returns_422(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.delete("/api/tasks/stress-task/items/STRESS-1")
        assert resp.status_code == 422

    def test_missing_token_on_assign_returns_422(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.post("/api/tasks/stress-task/items/STRESS-1/assign")
        assert resp.status_code == 422

    def test_missing_token_on_comment_returns_422(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "no token"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Concurrent-style operations
# ---------------------------------------------------------------------------


class TestConcurrentOperations:
    def test_create_100_items_unique_sequential_ids(self, client):
        _post_task(client)
        token = _register(client)
        ids = []
        for i in range(100):
            resp = client.post(
                "/api/tasks/stress-task/items",
                json={"title": f"Item {i}"},
                params={"token": token},
            )
            assert resp.status_code == 201
            ids.append(resp.json()["id"])
        # All IDs must be unique
        assert len(set(ids)) == 100
        # IDs should be sequential: STRESS-1 through STRESS-100
        expected = [f"STRESS-{i}" for i in range(1, 101)]
        assert ids == expected



# ---------------------------------------------------------------------------
# 5. Data integrity
# ---------------------------------------------------------------------------


class TestDataIntegrity:
    def test_parent_child_grandchild_delete_chain(self, client):
        """Create parent → child → grandchild, delete in reverse order."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "Parent"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "Child", "parent_id": "STRESS-1"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "Grandchild", "parent_id": "STRESS-2"}, params={"token": token})

        # Cannot delete child while grandchild exists
        r = client.delete("/api/tasks/stress-task/items/STRESS-2", params={"token": token})
        assert r.status_code == 409

        # Delete grandchild first
        r = client.delete("/api/tasks/stress-task/items/STRESS-3", params={"token": token})
        assert r.status_code == 204

        # Now delete child
        r = client.delete("/api/tasks/stress-task/items/STRESS-2", params={"token": token})
        assert r.status_code == 204

        # Now delete parent
        r = client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})
        assert r.status_code == 204

    def test_comment_count_accurate_after_create_and_delete(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})

        # Add 3 comments
        comment_ids = []
        for i in range(3):
            r = client.post(
                "/api/tasks/stress-task/items/STRESS-1/comments",
                json={"content": f"comment {i}"},
                params={"token": token},
            )
            comment_ids.append(r.json()["id"])

        item_resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        assert item_resp.json()["comment_count"] == 3

        # Delete one comment
        client.delete(f"/api/tasks/stress-task/items/STRESS-1/comments/{comment_ids[0]}", params={"token": token})

        item_resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        assert item_resp.json()["comment_count"] == 2

    def test_soft_delete_item_also_soft_deletes_comments(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "comment 1"},
            params={"token": token},
        )
        client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "comment 2"},
            params={"token": token},
        )

        # Soft-delete the item
        client.delete("/api/tasks/stress-task/items/STRESS-1", params={"token": token})

        # Comments should also be soft-deleted — verify via DB directly
        with psycopg.connect(_db.DATABASE_URL) as conn:
            rows = conn.execute(
                "SELECT * FROM item_comments WHERE item_id = %s AND deleted_at IS NULL",
                ("STRESS-1",),
            ).fetchall()
        assert len(rows) == 0

    def test_children_list_excludes_soft_deleted_children(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "Parent"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "Child 1", "parent_id": "STRESS-1"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "Child 2", "parent_id": "STRESS-1"}, params={"token": token})

        # Soft-delete child 1 (no grandchildren so delete allowed)
        client.delete("/api/tasks/stress-task/items/STRESS-2", params={"token": token})

        # Get parent — children list should only have child 2
        resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        assert resp.status_code == 200
        children = resp.json()["children"]
        assert len(children) == 1
        assert children[0]["id"] == "STRESS-3"

    def test_list_items_excludes_soft_deleted(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "Keep"}, params={"token": token})
        client.post("/api/tasks/stress-task/items", json={"title": "Delete me"}, params={"token": token})
        client.delete("/api/tasks/stress-task/items/STRESS-2", params={"token": token})

        resp = client.get("/api/tasks/stress-task/items")
        assert resp.status_code == 200
        items = resp.json()["items"]
        ids = [i["id"] for i in items]
        assert "STRESS-1" in ids
        assert "STRESS-2" not in ids

    def test_comment_count_zero_after_all_comments_deleted(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        r = client.post(
            "/api/tasks/stress-task/items/STRESS-1/comments",
            json={"content": "only comment"},
            params={"token": token},
        )
        comment_id = r.json()["id"]
        client.delete(f"/api/tasks/stress-task/items/STRESS-1/comments/{comment_id}", params={"token": token})

        item_resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        assert item_resp.json()["comment_count"] == 0

    def test_comment_count_in_list_view_matches_get_view(self, client):
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/stress-task/items", json={"title": "item"}, params={"token": token})
        for i in range(5):
            client.post(
                "/api/tasks/stress-task/items/STRESS-1/comments",
                json={"content": f"c{i}"},
                params={"token": token},
            )

        get_resp = client.get("/api/tasks/stress-task/items/STRESS-1")
        list_resp = client.get("/api/tasks/stress-task/items")

        get_count = get_resp.json()["comment_count"]
        list_count = list_resp.json()["items"][0]["comment_count"]
        assert get_count == list_count == 5
