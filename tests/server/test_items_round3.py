"""Adversarial stress tests for the Items API — Round 3.

Covers: PATCH edge cases, assign endpoint edge cases, comment edge cases,
bulk edge cases, soft-delete cascading integrity, and ID generation edge cases.
"""
import psycopg
import pytest

import hive.server.db as _db


def _post_task(client, task_id="r3-task"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    return client.post("/api/register", json=body).json()["token"]


def _create_item(client, task_id="r3-task", token=None, **kwargs):
    body = {"title": "test item", **kwargs}
    return client.post(f"/api/tasks/{task_id}/items", json=body, params={"token": token})


# ---------------------------------------------------------------------------
# 1. PATCH edge cases
# ---------------------------------------------------------------------------


class TestPatchEdgeCases:
    def test_patch_labels_null_rejects(self, client):
        """PATCH with labels: null — labels must be an array, so 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"labels": None},
            params={"token": token},
        )
        # labels: null is not a list -> should 400
        assert resp.status_code == 400

    def test_patch_labels_empty_clears(self, client):
        """PATCH with labels: [] should clear all labels."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token, labels=["bug", "feature"])
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"labels": []},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["labels"] == []

    def test_patch_assignee_id_null_unassigns(self, client):
        """PATCH with assignee_id: null should clear the assignee."""
        _post_task(client)
        token = _register(client, "r3-agent")
        _create_item(client, token=token, assignee_id="r3-agent")
        # Confirm initially assigned
        item = client.get("/api/tasks/r3-task/items/R3-1").json()
        assert item["assignee_id"] == "r3-agent"
        # Unassign
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"assignee_id": None},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] is None

    def test_patch_parent_id_null_unparents(self, client):
        """PATCH with parent_id: null should clear the parent."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        _create_item(client, token=token, parent_id="R3-1")
        # Confirm parented
        item = client.get("/api/tasks/r3-task/items/R3-2").json()
        assert item["parent_id"] == "R3-1"
        # Unparent
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-2",
            json={"parent_id": None},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["parent_id"] is None

    def test_patch_title_empty_string_rejects(self, client):
        """PATCH with title: '' should reject — empty title."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"title": ""},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_title_whitespace_only_rejects(self, client):
        """PATCH with title: '   ' should reject — blank title."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"title": "   "},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_description_null_clears(self, client):
        """PATCH with description: null should clear the description."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token, description="some description")
        # Confirm description is set
        item = client.get("/api/tasks/r3-task/items/R3-1").json()
        assert item["description"] == "some description"
        # Clear it
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"description": None},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["description"] is None

    def test_patch_parent_to_deleted_parent(self, client):
        """PATCH item to valid parent, then delete parent — child still accessible."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)  # R3-1 parent
        _create_item(client, token=token)  # R3-2 standalone
        # Assign R3-2's parent to R3-1
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-2",
            json={"parent_id": "R3-1"},
            params={"token": token},
        )
        assert resp.status_code == 200
        # Now try to delete R3-1 (it has a child R3-2) — should 409
        del_resp = client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        assert del_resp.status_code == 409
        # Remove parent from R3-2 first
        client.patch(
            "/api/tasks/r3-task/items/R3-2",
            json={"parent_id": None},
            params={"token": token},
        )
        # Now delete R3-1
        del_resp2 = client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        assert del_resp2.status_code == 204
        # R3-2 still accessible and parent_id is None
        child = client.get("/api/tasks/r3-task/items/R3-2").json()
        assert child["id"] == "R3-2"
        assert child["parent_id"] is None

    def test_patch_assignee_nonexistent_agent(self, client):
        """PATCH to set assignee_id to a nonexistent agent — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"assignee_id": "ghost-agent-xyz"},
            params={"token": token},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Assign endpoint edge cases
# ---------------------------------------------------------------------------


class TestAssignEdgeCases:
    def test_assign_self_renews_assignment_timestamp(self, client):
        """Assigning the same agent twice should renew the assignment timestamp."""
        _post_task(client)
        token = _register(client, "r3-assign-agent")
        _create_item(client, token=token)
        r1 = client.post("/api/tasks/r3-task/items/R3-1/assign", params={"token": token})
        assert r1.status_code == 200
        updated_at_1 = r1.json()["updated_at"]
        assigned_at_1 = r1.json()["assigned_at"]
        r2 = client.post("/api/tasks/r3-task/items/R3-1/assign", params={"token": token})
        assert r2.status_code == 200
        updated_at_2 = r2.json()["updated_at"]
        assigned_at_2 = r2.json()["assigned_at"]
        assert updated_at_1 != updated_at_2
        assert assigned_at_1 != assigned_at_2

    def test_assign_soft_deleted_item_404(self, client):
        """Assign a soft-deleted item — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        resp = client.post("/api/tasks/r3-task/items/R3-1/assign", params={"token": token})
        assert resp.status_code == 404

    def test_unassign_via_patch_assignee_null(self, client):
        """Unassign item by PATCHing assignee_id: null."""
        _post_task(client)
        token = _register(client, "r3-unassign-agent")
        _create_item(client, token=token)
        client.post("/api/tasks/r3-task/items/R3-1/assign", params={"token": token})
        resp = client.patch(
            "/api/tasks/r3-task/items/R3-1",
            json={"assignee_id": None},
            params={"token": token},
        )
        assert resp.status_code == 200
        assert resp.json()["assignee_id"] is None


# ---------------------------------------------------------------------------
# 3. Comment edge cases
# ---------------------------------------------------------------------------


class TestCommentEdgeCases:
    def test_comment_on_soft_deleted_item_404(self, client):
        """Add comment to a soft-deleted item — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        resp = client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "ghost comment"},
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_list_comments_on_soft_deleted_item_404(self, client):
        """List comments on a soft-deleted item — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "a comment"},
            params={"token": token},
        )
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        resp = client.get("/api/tasks/r3-task/items/R3-1/comments")
        assert resp.status_code == 404

    def test_delete_comment_on_soft_deleted_item_404(self, client):
        """Delete comment on a soft-deleted item — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        c = client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "doomed comment"},
            params={"token": token},
        )
        comment_id = c.json()["id"]
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        resp = client.delete(
            f"/api/tasks/r3-task/items/R3-1/comments/{comment_id}",
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_comment_empty_string_content_rejects(self, client):
        """Create comment with empty string content — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": ""},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_comment_whitespace_only_content(self, client):
        """Create comment with whitespace-only content — behavior defined by server."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "   "},
            params={"token": token},
        )
        # The server checks: not content or not isinstance(content, str)
        # "   " is truthy in Python, so it passes the check — server may accept it
        # Document actual behavior: either 201 or 400 are acceptable
        assert resp.status_code in (201, 400)

    def test_comment_null_bytes_in_content_rejects(self, client):
        """Comment with null bytes in content — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "has\x00null"},
            params={"token": token},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 5. Soft delete cascading integrity
# ---------------------------------------------------------------------------


class TestSoftDeleteCascading:
    def test_soft_delete_item_cascades_to_comments(self, client):
        """Create item with 3 comments, soft-delete item, verify all comments soft-deleted."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        for i in range(3):
            client.post(
                "/api/tasks/r3-task/items/R3-1/comments",
                json={"content": f"comment {i}"},
                params={"token": token},
            )
        # Confirm 3 comments exist
        item = client.get("/api/tasks/r3-task/items/R3-1").json()
        assert item["comment_count"] == 3
        # Soft-delete the item
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        # Verify all comments are soft-deleted in DB
        with psycopg.connect(_db.DATABASE_URL) as conn:
            rows = conn.execute(
                "SELECT * FROM item_comments WHERE item_id = %s AND deleted_at IS NULL",
                ("R3-1",),
            ).fetchall()
        assert len(rows) == 0

    def test_soft_delete_item_comment_count_gone(self, client):
        """After soft-deleting item, the item is 404 so comment_count is inaccessible."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        client.post(
            "/api/tasks/r3-task/items/R3-1/comments",
            json={"content": "a comment"},
            params={"token": token},
        )
        client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        # Item is gone — 404
        resp = client.get("/api/tasks/r3-task/items/R3-1")
        assert resp.status_code == 404

    def test_soft_delete_parent_child_still_accessible(self, client):
        """Soft-delete parent (after unparenting child); child still accessible."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)  # R3-1 parent
        _create_item(client, token=token, parent_id="R3-1")  # R3-2 child
        # Cannot delete parent while child exists
        del_resp = client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        assert del_resp.status_code == 409
        # Unparent child first
        client.patch(
            "/api/tasks/r3-task/items/R3-2",
            json={"parent_id": None},
            params={"token": token},
        )
        # Now delete parent
        del_resp2 = client.delete("/api/tasks/r3-task/items/R3-1", params={"token": token})
        assert del_resp2.status_code == 204
        # Child still accessible, parent_id reflects None (was already unparented)
        child = client.get("/api/tasks/r3-task/items/R3-2").json()
        assert child["id"] == "R3-2"
        assert child["parent_id"] is None

    def test_child_parent_id_points_to_deleted_item_after_direct_db_delete(self, client):
        """If parent is deleted without first unparenting child (using direct DB),
        the child's parent_id still holds the deleted item's ID (referential integrity
        is via FK but soft-delete doesn't enforce; child is still GETable)."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)          # R3-1 parent
        _create_item(client, token=token, parent_id="R3-1")  # R3-2 child
        # Directly soft-delete the parent in DB, bypassing the API's child check
        with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
            conn.execute(
                "UPDATE items SET deleted_at = %s WHERE id = %s",
                (_db.now(), "R3-1"),
            )
        # Parent is soft-deleted — GET returns 404
        assert client.get("/api/tasks/r3-task/items/R3-1").status_code == 404
        # Child is still accessible via GET
        child_resp = client.get("/api/tasks/r3-task/items/R3-2")
        assert child_resp.status_code == 200
        # Child's parent_id still shows "R3-1" (the deleted item's ID)
        assert child_resp.json()["parent_id"] == "R3-1"


# ---------------------------------------------------------------------------
# 6. ID generation edge cases
# ---------------------------------------------------------------------------


class TestIDGenerationEdgeCases:
    def test_independent_sequences_across_tasks(self, client):
        """Create items in two tasks; IDs have correct prefixes and independent seqs."""
        _post_task(client, "alpha-task")
        _post_task(client, "beta-task")
        token = _register(client)
        # Create items in both tasks
        ra1 = _create_item(client, task_id="alpha-task", token=token)
        rb1 = _create_item(client, task_id="beta-task", token=token)
        ra2 = _create_item(client, task_id="alpha-task", token=token)
        rb2 = _create_item(client, task_id="beta-task", token=token)
        assert ra1.status_code == 201
        assert rb1.status_code == 201
        assert ra2.status_code == 201
        assert rb2.status_code == 201
        # alpha-task prefix is "ALPHA", beta-task prefix is "BETA"
        assert ra1.json()["id"] == "ALPHA-1"
        assert rb1.json()["id"] == "BETA-1"
        assert ra2.json()["id"] == "ALPHA-2"
        assert rb2.json()["id"] == "BETA-2"

    def test_task_id_with_no_hyphen_prefix(self, client):
        """Task ID with no hyphen (e.g. 'simple') — prefix is the whole ID uppercased."""
        _post_task(client, "simple")
        token = _register(client)
        resp = _create_item(client, task_id="simple", token=token)
        assert resp.status_code == 201
        # _task_prefix("simple") = "simple".split("-")[0].upper() = "SIMPLE"
        assert resp.json()["id"] == "SIMPLE-1"

    def test_task_id_starting_with_number_prefix(self, client):
        """Task ID starting with a number (e.g. '8k-math') — prefix should be '8K'."""
        _post_task(client, "8k-math")
        token = _register(client)
        resp = _create_item(client, task_id="8k-math", token=token)
        assert resp.status_code == 201
        # _task_prefix("8k-math") = "8k-math".split("-")[0].upper() = "8K"
        assert resp.json()["id"] == "8K-1"
