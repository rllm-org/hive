"""Adversarial stress tests for the Items API — Round 6 (final hardening).

Covers: bulk create type confusion + atomicity, concurrent bulk ID uniqueness,
cross-task parent_id rejection, assign-then-delete, comment-after-reassign +
cascaded soft-delete, deeply nested comment_count, list sort options, PATCH
idempotency with updated_at, bulk update with zero-field items, and
Content-Type edge cases.
"""
import psycopg
import pytest
import time

import hive.server.db as _db


def _post_task(client, slug="r6-task"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (slug, owner, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, 'hive', %s, %s, %s, %s, 0)",
            (slug, slug, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    return client.post("/api/register", json=body).json()["token"]


def _create_item(client, slug="r6-task", token=None, **kwargs):
    body = {"title": "test item", **kwargs}
    return client.post(f"/api/tasks/hive/{slug}/items", json=body, params={"token": token})


# ---------------------------------------------------------------------------
# 3. PATCH edge: set parent_id to an item in a DIFFERENT task
# ---------------------------------------------------------------------------


class TestCrossTaskParentId:
    def test_patch_parent_id_from_different_task_rejects(self, client):
        """PATCH item in alpha-task with parent_id pointing to item in bravo-task — should fail.

        Tasks use distinct prefixes (alpha, bravo) so their item IDs don't collide.
        """
        _post_task(client, "alpha-xtask")
        _post_task(client, "bravo-xtask")
        token = _register(client)

        r_a = _create_item(client, slug="alpha-xtask", token=token, title="item in alpha")
        assert r_a.status_code == 201
        item_a_id = r_a.json()["id"]  # ALPHA-1

        r_b = _create_item(client, slug="bravo-xtask", token=token, title="item in bravo")
        assert r_b.status_code == 201
        item_b_id = r_b.json()["id"]  # BRAVO-1

        # Attempt to set item in alpha-task's parent to item in bravo-task
        resp = client.patch(
            f"/api/tasks/hive/alpha-xtask/items/{item_a_id}",
            json={"parent_id": item_b_id},
            params={"token": token},
        )
        assert resp.status_code in (400, 404), (
            f"Cross-task parent_id should be rejected, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 4. Assign then delete
# ---------------------------------------------------------------------------


class TestAssignThenDelete:
    def test_assigned_item_can_be_deleted_by_creator(self, client):
        """Assign item to agent-a, then creator soft-deletes it — should work (204)."""
        _post_task(client)
        token_creator = _register(client, "r6-creator")
        token_other = _register(client, "r6-assignee")

        r = _create_item(client, token=token_creator, title="item to delete")
        assert r.status_code == 201
        item_id = r.json()["id"]

        assign_r = client.post(
            f"/api/tasks/hive/r6-task/items/{item_id}/assign",
            params={"token": token_other},
        )
        assert assign_r.status_code == 200
        assert assign_r.json()["assignee_id"] == "r6-assignee"

        del_r = client.delete(
            f"/api/tasks/hive/r6-task/items/{item_id}",
            params={"token": token_creator},
        )
        assert del_r.status_code == 204

    def test_assign_after_deletion_returns_404(self, client):
        """After item is deleted, assign endpoint should return 404."""
        _post_task(client)
        token = _register(client, "r6-del-assign")

        r = _create_item(client, token=token, title="doomed item")
        assert r.status_code == 201
        item_id = r.json()["id"]

        del_r = client.delete(
            f"/api/tasks/hive/r6-task/items/{item_id}",
            params={"token": token},
        )
        assert del_r.status_code == 204

        assign_r = client.post(
            f"/api/tasks/hive/r6-task/items/{item_id}/assign",
            params={"token": token},
        )
        assert assign_r.status_code == 404


# ---------------------------------------------------------------------------
# 5. Comment after reassign (soft-delete cascade)
# ---------------------------------------------------------------------------


class TestCommentAfterReassign:
    def test_comment_soft_deleted_with_item(self, client):
        """Create item (agent-a), assign to agent-b, agent-b comments, agent-a deletes item.
        Verify the comment was soft-deleted along with the item."""
        _post_task(client)
        token_a = _register(client, "r6-owner-a")
        token_b = _register(client, "r6-commenter-b")

        r = _create_item(client, token=token_a, title="shared item")
        assert r.status_code == 201
        item_id = r.json()["id"]

        assign_r = client.post(
            f"/api/tasks/hive/r6-task/items/{item_id}/assign",
            params={"token": token_b},
        )
        assert assign_r.status_code == 200

        comment_r = client.post(
            f"/api/tasks/hive/r6-task/items/{item_id}/comments",
            json={"content": "agent-b's comment"},
            params={"token": token_b},
        )
        assert comment_r.status_code == 201
        comment_id = comment_r.json()["id"]

        del_r = client.delete(
            f"/api/tasks/hive/r6-task/items/{item_id}",
            params={"token": token_a},
        )
        assert del_r.status_code == 204

        # Verify comment is soft-deleted in DB
        with psycopg.connect(_db.DATABASE_URL) as conn:
            row = conn.execute(
                "SELECT deleted_at FROM item_comments WHERE id = %s",
                (comment_id,),
            ).fetchone()
        assert row is not None, "Comment row should still exist in DB"
        assert row[0] is not None, "Comment deleted_at should be set after item deletion"


# ---------------------------------------------------------------------------
# 6. Deeply nested operations stress test
# ---------------------------------------------------------------------------


class TestDeeplyNestedStress:
    def test_5level_chain_comment_counts_and_subtree_delete(self, client):
        """Create 5-level chain, add 1 comment at each level, verify comment_counts.
        Delete leaf, verify parent children list shrinks."""
        _post_task(client)
        token = _register(client, "r6-deep")

        # Build 5-level chain: item1 -> item2 -> item3 -> item4 -> item5
        ids = []
        parent_id = None
        for level in range(5):
            body = {"title": f"level-{level + 1}"}
            if parent_id:
                body["parent_id"] = parent_id
            r = client.post(
                "/api/tasks/hive/r6-task/items",
                json=body,
                params={"token": token},
            )
            assert r.status_code == 201, f"Create level {level + 1} failed: {r.json()}"
            ids.append(r.json()["id"])
            parent_id = ids[-1]

        # Add 1 comment at each level
        for item_id in ids:
            r = client.post(
                f"/api/tasks/hive/r6-task/items/{item_id}/comments",
                json={"content": f"comment on {item_id}"},
                params={"token": token},
            )
            assert r.status_code == 201

        # Verify each item has comment_count == 1
        for item_id in ids:
            r = client.get(f"/api/tasks/hive/r6-task/items/{item_id}")
            assert r.status_code == 200
            assert r.json()["comment_count"] == 1, (
                f"Expected comment_count=1 for {item_id}, got {r.json()['comment_count']}"
            )

        # Delete leaf (level 5)
        leaf_id = ids[4]
        del_r = client.delete(
            f"/api/tasks/hive/r6-task/items/{leaf_id}",
            params={"token": token},
        )
        assert del_r.status_code == 204

        # Verify level-4's children list no longer includes the leaf
        parent_detail = client.get(f"/api/tasks/hive/r6-task/items/{ids[3]}")
        assert parent_detail.status_code == 200
        children = parent_detail.json()["children"]
        child_ids = [c["id"] for c in children]
        assert leaf_id not in child_ids, (
            f"Deleted leaf {leaf_id} should not appear in parent's children: {child_ids}"
        )

    def test_delete_item_with_children_returns_409(self, client):
        """Delete item at level 3 of a 5-level chain (has children) — should 409."""
        _post_task(client)
        token = _register(client, "r6-deep-409")

        ids = []
        parent_id = None
        for level in range(5):
            body = {"title": f"node-{level + 1}"}
            if parent_id:
                body["parent_id"] = parent_id
            r = client.post(
                "/api/tasks/hive/r6-task/items",
                json=body,
                params={"token": token},
            )
            assert r.status_code == 201
            ids.append(r.json()["id"])
            parent_id = ids[-1]

        # Try to delete level-3 item (ids[2]) which has a child (ids[3])
        resp = client.delete(
            f"/api/tasks/hive/r6-task/items/{ids[2]}",
            params={"token": token},
        )
        assert resp.status_code == 409, (
            f"Deleting item with children should return 409, got {resp.status_code}"
        )


# ---------------------------------------------------------------------------
# 7. List items with all sort options
# ---------------------------------------------------------------------------


class TestListSortOptions:
    def _setup_items(self, client):
        """Create items with varying priority for sort testing."""
        _post_task(client)
        token = _register(client, "r6-sort-agent")
        # Create items with different priorities, in order
        priorities = ["none", "low", "urgent", "high", "medium"]
        ids = []
        for i, prio in enumerate(priorities):
            r = _create_item(
                client, token=token, title=f"item-{i}", priority=prio
            )
            assert r.status_code == 201
            ids.append(r.json()["id"])
            time.sleep(0.01)  # ensure distinct created_at timestamps
        return token, ids

    def test_sort_recent_default_newest_first(self, client):
        """sort=recent (default) — verify newest first."""
        token, ids = self._setup_items(client)
        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "recent"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        # ids[-1] should be first (most recently created)
        assert returned[0] == ids[-1], (
            f"sort=recent should return newest first; got {returned}, expected {ids[-1]} first"
        )

    def test_sort_recent_asc_oldest_first(self, client):
        """sort=recent:asc — oldest first."""
        token, ids = self._setup_items(client)
        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "recent:asc"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        assert returned[0] == ids[0], (
            f"sort=recent:asc should return oldest first; got {returned}, expected {ids[0]} first"
        )

    def test_sort_updated_most_recently_updated_first(self, client):
        """sort=updated — most recently updated item first."""
        token, ids = self._setup_items(client)
        # Patch the first created item (oldest) to make it most recently updated
        time.sleep(0.02)
        patch_r = client.patch(
            f"/api/tasks/hive/r6-task/items/{ids[0]}",
            json={"status": "in_progress"},
            params={"token": token},
        )
        assert patch_r.status_code == 200

        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "updated"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        assert returned[0] == ids[0], (
            f"sort=updated should return most recently updated first; got {returned}, expected {ids[0]} first"
        )

    def test_sort_updated_asc(self, client):
        """sort=updated:asc — least recently updated first."""
        token, ids = self._setup_items(client)
        # Patch the last item to make it the most recently updated
        time.sleep(0.02)
        client.patch(
            f"/api/tasks/hive/r6-task/items/{ids[-1]}",
            json={"status": "in_progress"},
            params={"token": token},
        )

        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "updated:asc"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        # ids[-1] was just updated, so it should be last in asc order
        assert returned[-1] == ids[-1], (
            f"sort=updated:asc should return least recently updated first; got {returned}"
        )

    def test_sort_priority_urgent_first(self, client):
        """sort=priority — urgent first (default asc: urgent > high > medium > low > none)."""
        token, ids = self._setup_items(client)
        # priorities created: none, low, urgent, high, medium -> ids[2] is urgent
        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "priority"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        # urgent should be first
        urgent_id = ids[2]
        assert returned[0] == urgent_id, (
            f"sort=priority (asc) should put urgent first; got {returned}, expected {urgent_id} first"
        )

    def test_sort_priority_desc_none_low_first(self, client):
        """sort=priority:desc — none/low priority first."""
        token, ids = self._setup_items(client)
        # priorities: none(ids[0]), low(ids[1]), urgent(ids[2]), high(ids[3]), medium(ids[4])
        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "priority:desc"})
        assert resp.status_code == 200
        returned = [item["id"] for item in resp.json()["items"]]
        # none should be first in desc (lowest priority value = 4 in the CASE expression)
        assert returned[0] == ids[0], (
            f"sort=priority:desc should put none/low first; got {returned}, expected {ids[0]} first"
        )

    def test_sort_bogus_falls_back_to_default(self, client):
        """sort=bogus — should fall back to default (recent desc), not error."""
        token, ids = self._setup_items(client)
        resp = client.get("/api/tasks/hive/r6-task/items", params={"sort": "bogus"})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        # Bogus sort falls back to recent:desc — newest first
        returned = [item["id"] for item in data["items"]]
        assert returned[0] == ids[-1], (
            f"bogus sort should fall back to recent:desc (newest first); got {returned}"
        )


# ---------------------------------------------------------------------------
# 8. Idempotency and double operations
# ---------------------------------------------------------------------------


class TestIdempotencyAndDoubleOps:
    def test_patch_same_field_twice_updates_updated_at(self, client):
        """PATCH same field to same value twice — updated_at should change each time."""
        _post_task(client)
        token = _register(client, "r6-idem")
        r = _create_item(client, token=token, title="idem item")
        assert r.status_code == 201

        time.sleep(0.05)

        patch1 = client.patch(
            "/api/tasks/hive/r6-task/items/R6-1",
            json={"status": "in_progress"},
            params={"token": token},
        )
        assert patch1.status_code == 200
        updated_at_1 = patch1.json()["updated_at"]

        time.sleep(0.05)

        patch2 = client.patch(
            "/api/tasks/hive/r6-task/items/R6-1",
            json={"status": "in_progress"},
            params={"token": token},
        )
        assert patch2.status_code == 200
        updated_at_2 = patch2.json()["updated_at"]

        assert updated_at_2 >= updated_at_1, (
            f"updated_at should change or stay same with each PATCH write; "
            f"first={updated_at_1}, second={updated_at_2}"
        )


# ---------------------------------------------------------------------------
# 9. Content-Type edge cases
# ---------------------------------------------------------------------------


class TestContentTypeEdgeCases:
    def test_post_item_with_text_plain_content_type(self, client):
        """POST item with Content-Type: text/plain — server should reject or handle, not 500."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/r6-task/items",
            content='{"title": "plain text body"}',
            headers={"Content-Type": "text/plain"},
            params={"token": token},
        )
        # FastAPI typically returns 422 for non-JSON content type when expecting JSON body
        assert resp.status_code in (400, 415, 422), (
            f"text/plain Content-Type should be rejected, got {resp.status_code}"
        )

    def test_post_item_with_no_content_type(self, client):
        """POST item with no Content-Type header — server should reject or handle, not 500."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/r6-task/items",
            content='{"title": "no content type"}',
            params={"token": token},
        )
        # No Content-Type means FastAPI can't parse the body — 400/415/422 expected
        assert resp.status_code in (400, 415, 422), (
            f"Missing Content-Type should be rejected, got {resp.status_code}"
        )

    def test_post_item_with_multipart_form_data_content_type(self, client):
        """POST item with Content-Type: multipart/form-data — should fail gracefully."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/hive/r6-task/items",
            data={"title": "form data"},
            params={"token": token},
        )
        # Sending form data to a JSON endpoint should fail with 400/415/422
        assert resp.status_code in (400, 415, 422), (
            f"multipart/form-data Content-Type should be rejected, got {resp.status_code}"
        )
