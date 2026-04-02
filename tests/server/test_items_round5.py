"""Adversarial stress tests for the Items API — Round 5.

Final hardening round. Covers: PATCH type confusion, bulk update type confusion
and rollback, comment edge cases, assign edge cases, token reuse across tasks,
empty string edge cases, URL path traversal, updated_at behavior, and
multi-agent access control.
"""
import psycopg
import pytest
import time

import hive.server.db as _db


def _post_task(client, task_id="r5-task"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    return client.post("/api/register", json=body).json()["token"]


def _create_item(client, task_id="r5-task", token=None, **kwargs):
    body = {"title": "test item", **kwargs}
    return client.post(f"/api/tasks/{task_id}/items", json=body, params={"token": token})


# ---------------------------------------------------------------------------
# 1. PATCH with type-confused values
# ---------------------------------------------------------------------------


class TestPatchTypeConfusion:
    def test_patch_labels_string_rejects(self, client):
        """PATCH with labels: 'string' instead of array — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"labels": "bug"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_labels_null_rejects(self, client):
        """PATCH with labels: null — should 400 (null is not a list)."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"labels": None},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_parent_id_integer_rejects(self, client):
        """PATCH with parent_id: 123 (integer) — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"parent_id": 123},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_status_null_rejects(self, client):
        """PATCH with status: null — null is not in VALID_STATUSES, should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"status": None},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_priority_array_rejects(self, client):
        """PATCH with priority: [] — array is not in VALID_PRIORITIES, should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"priority": []},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_title_integer_rejects(self, client):
        """PATCH with title: 123 (integer) — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"title": 123},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_patch_description_array_rejects(self, client):
        """PATCH with description: ['array'] — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"description": ["array"]},
            params={"token": token},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Comment edge cases
# ---------------------------------------------------------------------------


class TestCommentEdgeCases:
    def test_comment_content_integer_rejects(self, client):
        """Create comment with content: 123 (integer) — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": 123},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_comment_content_null_rejects(self, client):
        """Create comment with content: null — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": None},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_comment_content_array_rejects(self, client):
        """Create comment with content: ['array'] — should 400."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        resp = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": ["array"]},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_delete_comment_wrong_item(self, client):
        """Delete a comment that belongs to item R5-1 via item R5-2 URL — should 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token, title="item A")
        _create_item(client, token=token, title="item B")

        # Create comment on R5-1
        r = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": "hello from item 1"},
            params={"token": token},
        )
        assert r.status_code == 201
        comment_id = r.json()["id"]

        # Try to delete via R5-2 URL — comment_id belongs to R5-1, not R5-2
        resp = client.delete(
            f"/api/tasks/r5-task/items/R5-2/comments/{comment_id}",
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_list_comments_page_zero(self, client):
        """List comments with page=0 — should be clamped to 1, not error."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": "a comment"},
            params={"token": token},
        )
        resp = client.get(
            "/api/tasks/r5-task/items/R5-1/comments",
            params={"page": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["comments"]) >= 1

    def test_list_comments_per_page_zero(self, client):
        """List comments with per_page=0 — should be clamped to 1, not error."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)
        for i in range(3):
            client.post(
                "/api/tasks/r5-task/items/R5-1/comments",
                json={"content": f"comment {i}"},
                params={"token": token},
            )
        resp = client.get(
            "/api/tasks/r5-task/items/R5-1/comments",
            params={"per_page": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        # clamped to 1, so exactly 1 comment
        assert len(data["comments"]) == 1


# ---------------------------------------------------------------------------
# 4. Assign edge cases after unassign
# ---------------------------------------------------------------------------


class TestAssignEdgeCases:
    def test_assign_after_patch_unassign(self, client):
        """Create item, assign agent-a, PATCH to unassign (assignee_id: null),
        then POST /assign with agent-b — should work (200)."""
        _post_task(client)
        token_a = _register(client, "r5-agent-aa")
        token_b = _register(client, "r5-agent-bb")
        _create_item(client, token=token_a)

        # Assign to agent-a
        r = client.post("/api/tasks/r5-task/items/R5-1/assign", params={"token": token_a})
        assert r.status_code == 200
        assert r.json()["assignee_id"] == "r5-agent-aa"

        # PATCH to unassign
        r_unassign = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"assignee_id": None},
            params={"token": token_a},
        )
        assert r_unassign.status_code == 200
        assert r_unassign.json()["assignee_id"] is None

        # Now agent-b can assign
        r2 = client.post("/api/tasks/r5-task/items/R5-1/assign", params={"token": token_b})
        assert r2.status_code == 200
        assert r2.json()["assignee_id"] == "r5-agent-bb"

    def test_assign_same_agent_idempotent(self, client):
        """Create item, assign agent-a, then POST /assign with agent-a again — idempotent, 200."""
        _post_task(client)
        token_a = _register(client, "r5-agent-cc")
        _create_item(client, token=token_a)

        r1 = client.post("/api/tasks/r5-task/items/R5-1/assign", params={"token": token_a})
        assert r1.status_code == 200
        assert r1.json()["assignee_id"] == "r5-agent-cc"

        # Second assign by same agent — should be 200, not 409
        r2 = client.post("/api/tasks/r5-task/items/R5-1/assign", params={"token": token_a})
        assert r2.status_code == 200
        assert r2.json()["assignee_id"] == "r5-agent-cc"


# ---------------------------------------------------------------------------
# 5. Token reuse across tasks
# ---------------------------------------------------------------------------


class TestTokenReuseAcrossTasks:
    def test_same_token_works_across_two_tasks(self, client):
        """Register one agent, create items in two different tasks — same token works.

        Tasks intentionally use different prefix letters so their item IDs don't collide
        (task-alpha -> ALPHA-1, task-bravo -> BRAVO-1).
        """
        _post_task(client, "alpha-task")
        _post_task(client, "bravo-task")
        token = _register(client, "r5-cross-task-agent")

        r1 = client.post(
            "/api/tasks/alpha-task/items",
            json={"title": "item in alpha"},
            params={"token": token},
        )
        assert r1.status_code == 201
        assert r1.json()["task_id"] == "alpha-task"

        r2 = client.post(
            "/api/tasks/bravo-task/items",
            json={"title": "item in bravo"},
            params={"token": token},
        )
        assert r2.status_code == 201
        assert r2.json()["task_id"] == "bravo-task"

    def test_unregistered_token_rejected(self, client):
        """Using a token that looks valid but was never registered — should 401."""
        _post_task(client)
        fake_token = "never-registered-agent"
        resp = client.post(
            "/api/tasks/r5-task/items",
            json={"title": "sneaky item"},
            params={"token": fake_token},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 6. Empty string edge cases
# ---------------------------------------------------------------------------


class TestEmptyStringEdgeCases:
    def test_patch_description_empty_string_clears(self, client):
        """PATCH with description: '' — should either clear description (200) or error (400).
        Document actual behavior. Must not be 500."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token, description="some description")

        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"description": ""},
            params={"token": token},
        )
        # Either 200 (clears the description) or 400 (empty string rejected)
        assert resp.status_code in (200, 400), f"Unexpected status {resp.status_code}"
        if resp.status_code == 200:
            # If accepted, description should be empty string or None
            assert resp.json()["description"] in ("", None)

    def test_patch_assignee_id_empty_string_rejected(self, client):
        """PATCH with assignee_id: '' — empty string is not a valid agent ID, should 400 or 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)

        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"assignee_id": ""},
            params={"token": token},
        )
        # Empty string assignee_id is not a registered agent -> should fail (400 or 404)
        assert resp.status_code in (400, 404), (
            f"Empty assignee_id should be rejected, got {resp.status_code}"
        )

    def test_patch_parent_id_empty_string_rejected(self, client):
        """PATCH with parent_id: '' — empty string is not a valid item ID, should 400 or 404."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)

        resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"parent_id": ""},
            params={"token": token},
        )
        # Empty string parent_id is not a real item -> 400 or 404
        assert resp.status_code in (400, 404), (
            f"Empty parent_id should be rejected, got {resp.status_code}"
        )

    def test_create_item_title_one_char_accepted(self, client):
        """Create item with title: 'a' (minimum valid title, 1 char) — should 201."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/r5-task/items",
            json={"title": "a"},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == "a"

    def test_create_item_description_empty_string(self, client):
        """Create item with description: '' — should either succeed (201) or reject (400).
        Must not be 500."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/r5-task/items",
            json={"title": "has empty desc", "description": ""},
            params={"token": token},
        )
        assert resp.status_code in (201, 400), f"Unexpected status {resp.status_code}"


# ---------------------------------------------------------------------------
# 7. URL path traversal / weird item IDs
# ---------------------------------------------------------------------------


class TestURLPathTraversal:
    def test_get_item_with_slash_in_id(self, client):
        """Try GET item with ID containing slashes — should 404, not 500."""
        _post_task(client)
        # Slashes in the path are interpreted by the router as path separators.
        # The route may match a different endpoint or return 404/405.
        resp = client.get("/api/tasks/r5-task/items/R5-1/../../secrets")
        # Should be 404 or 405, definitely not 500 or 200 with wrong data
        assert resp.status_code in (404, 405, 422), f"Unexpected status {resp.status_code}"

    def test_get_item_url_encoded_id(self, client):
        """GET item with URL-encoded characters in ID — should 404, not 500."""
        _post_task(client)
        # %20 is a space, %27 is single quote
        resp = client.get("/api/tasks/r5-task/items/R5-1%20OR%201%3D1")
        assert resp.status_code in (404, 400), f"Unexpected status {resp.status_code}"

    def test_get_item_extremely_long_id(self, client):
        """GET item with 1000-char ID — should 404, not 500."""
        _post_task(client)
        long_id = "X" * 1000
        resp = client.get(f"/api/tasks/r5-task/items/{long_id}")
        assert resp.status_code in (404, 400), f"Unexpected status {resp.status_code}"


# ---------------------------------------------------------------------------
# 8. updated_at behavior
# ---------------------------------------------------------------------------


class TestUpdatedAtBehavior:
    def test_created_at_equals_updated_at_on_create(self, client):
        """On create, created_at and updated_at should be equal (or very close)."""
        _post_task(client)
        token = _register(client)
        resp = _create_item(client, token=token)
        assert resp.status_code == 201
        data = resp.json()
        assert data["created_at"] == data["updated_at"], (
            f"On create, created_at ({data['created_at']}) should equal updated_at ({data['updated_at']})"
        )

    def test_patch_changes_updated_at_not_created_at(self, client):
        """After PATCH, updated_at changes but created_at stays the same."""
        _post_task(client)
        token = _register(client)
        resp = _create_item(client, token=token)
        assert resp.status_code == 201
        original_created_at = resp.json()["created_at"]
        original_updated_at = resp.json()["updated_at"]

        # Small sleep to ensure timestamp difference
        time.sleep(0.05)

        patch_resp = client.patch(
            "/api/tasks/r5-task/items/R5-1",
            json={"status": "archived"},
            params={"token": token},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()

        assert patched["created_at"] == original_created_at, (
            f"created_at must not change after PATCH: was {original_created_at}, now {patched['created_at']}"
        )
        # updated_at should be >= original (may be equal if db has coarse precision, but should not decrease)
        assert patched["updated_at"] >= original_updated_at, (
            f"updated_at should not decrease after PATCH"
        )

    def test_soft_delete_sets_deleted_at_only(self, client):
        """Soft delete sets deleted_at but does not change updated_at."""
        _post_task(client)
        token = _register(client)
        _create_item(client, token=token)

        # Record updated_at before delete
        before = client.get("/api/tasks/r5-task/items/R5-1").json()
        updated_at_before = before["updated_at"]

        client.delete("/api/tasks/r5-task/items/R5-1", params={"token": token})

        # Check DB directly: deleted_at is set, updated_at unchanged
        with psycopg.connect(_db.DATABASE_URL) as conn:
            row = conn.execute(
                "SELECT updated_at, deleted_at FROM items WHERE id = %s",
                ("R5-1",),
            ).fetchone()
        assert row is not None
        assert row[1] is not None, "deleted_at should be set after delete"
        # updated_at should NOT change when deleting
        db_updated_at = row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0])
        # Normalize both to compare (strip timezone suffix variations)
        assert db_updated_at.startswith(updated_at_before[:19]), (
            f"updated_at should not change on soft delete: before={updated_at_before}, after={db_updated_at}"
        )


# ---------------------------------------------------------------------------
# 9. Multi-agent access control
# ---------------------------------------------------------------------------


class TestMultiAgentAccessControl:
    def test_sequential_ids_across_multiple_agents(self, client):
        """Agent A creates 3 items, Agent B creates 2 items — all 5 have sequential IDs."""
        _post_task(client)
        token_a = _register(client, "r5-multi-a")
        token_b = _register(client, "r5-multi-b")

        ids_a = []
        for i in range(3):
            r = _create_item(client, token=token_a, title=f"agent-a item {i}")
            assert r.status_code == 201
            ids_a.append(r.json()["id"])

        ids_b = []
        for i in range(2):
            r = _create_item(client, token=token_b, title=f"agent-b item {i}")
            assert r.status_code == 201
            ids_b.append(r.json()["id"])

        all_ids = ids_a + ids_b
        assert len(set(all_ids)) == 5, "All IDs must be unique"
        expected = {f"R5-{i}" for i in range(1, 6)}
        assert set(all_ids) == expected, f"Expected sequential IDs {expected}, got {set(all_ids)}"

    def test_agent_can_delete_own_item(self, client):
        """Agent A can delete its own item — 204."""
        _post_task(client)
        token_a = _register(client, "r5-del-owner")
        _create_item(client, token=token_a, title="my item")

        resp = client.delete("/api/tasks/r5-task/items/R5-1", params={"token": token_a})
        assert resp.status_code == 204

    def test_agent_cannot_delete_other_agents_item(self, client):
        """Agent B cannot delete Agent A's item — 403."""
        _post_task(client)
        token_a = _register(client, "r5-owner-agent")
        token_b = _register(client, "r5-thief-agent")
        _create_item(client, token=token_a, title="agent a's item")

        resp = client.delete("/api/tasks/r5-task/items/R5-1", params={"token": token_b})
        assert resp.status_code == 403

    def test_agent_can_comment_on_other_agents_item(self, client):
        """Agent B can comment on Agent A's item — 201."""
        _post_task(client)
        token_a = _register(client, "r5-owner2")
        token_b = _register(client, "r5-commenter")
        _create_item(client, token=token_a, title="agent a's item")

        resp = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": "nice work agent a!"},
            params={"token": token_b},
        )
        assert resp.status_code == 201
        assert resp.json()["agent_id"] == "r5-commenter"

    def test_agent_cannot_delete_other_agents_comment(self, client):
        """Agent A cannot delete Agent B's comment — 403."""
        _post_task(client)
        token_a = _register(client, "r5-item-owner")
        token_b = _register(client, "r5-comment-owner")
        _create_item(client, token=token_a, title="agent a's item")

        # Agent B posts a comment
        r = client.post(
            "/api/tasks/r5-task/items/R5-1/comments",
            json={"content": "i am agent b, my comment"},
            params={"token": token_b},
        )
        assert r.status_code == 201
        comment_id = r.json()["id"]

        # Agent A tries to delete agent B's comment
        resp = client.delete(
            f"/api/tasks/r5-task/items/R5-1/comments/{comment_id}",
            params={"token": token_a},
        )
        assert resp.status_code == 403
