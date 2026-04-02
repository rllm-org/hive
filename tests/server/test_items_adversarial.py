"""Adversarial stress tests for the Items API — Round 2.

Covers: SQL injection, type confusion, cross-task isolation,
rapid sequential creation, pagination edge cases, unicode/special chars,
and double operations.
"""
import psycopg
import pytest

import hive.server.db as _db


def _post_task(client, task_id="adv-task"):
    with psycopg.connect(_db.DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tasks (id, name, description, repo_url, created_at, item_seq)"
            " VALUES (%s, %s, %s, %s, %s, 0)",
            (task_id, task_id, "test", "https://github.com/test", _db.now()),
        )


def _register(client, name=None):
    body = {"preferred_name": name} if name else {}
    return client.post("/api/register", json=body).json()["token"]


# ---------------------------------------------------------------------------
# 1. SQL injection attempts
# ---------------------------------------------------------------------------


class TestSQLInjection:
    def test_sql_injection_in_title(self, client):
        """SQL injection in title is stored literally via parameterized query."""
        _post_task(client)
        token = _register(client)
        malicious_title = "'; DROP TABLE items; --"
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": malicious_title},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == malicious_title

    def test_sql_injection_in_status_filter(self, client):
        """SQL injection in status query param is safe via parameterized query."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/adv-task/items", json={"title": "safe item"}, params={"token": token})
        # The injected status value is passed as a parameter, not interpolated
        resp = client.get(
            "/api/tasks/adv-task/items",
            params={"status": "todo'; DROP TABLE items; --"},
        )
        # Should return 200 with empty items (no items match that status) or 400, never 500
        assert resp.status_code in (200, 400)
        if resp.status_code == 200:
            assert resp.json()["items"] == []

    def test_sql_injection_in_sort_param(self, client):
        """SQL injection in sort param is defused by the allowlist lookup."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/adv-task/items", json={"title": "item"}, params={"token": token})
        # _parse_sort does allowed.get(field, default) so unknown field gets default sort
        resp = client.get(
            "/api/tasks/adv-task/items",
            params={"sort": "recent; DROP TABLE items"},
        )
        assert resp.status_code == 200

    def test_sql_injection_label_name(self, client):
        """Label with SQL-like chars is rejected by _LABEL_RE validation."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "labels": ["bug'; DROP TABLE items; --"]},
            params={"token": token},
        )
        # _LABEL_RE only allows [a-zA-Z0-9_-], so apostrophe/space/semicolon are rejected
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. Type confusion / malformed input
# ---------------------------------------------------------------------------


class TestTypeConfusion:
    def test_labels_as_string(self, client):
        """Sending labels as a string instead of array — returns 400."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "labels": "bug"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_labels_as_null(self, client):
        """Sending labels as null — returns 400."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "labels": None},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_status_as_integer(self, client):
        """Sending status as integer is rejected by _validate_fields."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "status": 1},
            params={"token": token},
        )
        # 1 not in VALID_STATUSES -> 400
        assert resp.status_code == 400

    def test_priority_as_boolean(self, client):
        """Sending priority as boolean is rejected by _validate_fields."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "priority": True},
            params={"token": token},
        )
        # True not in VALID_PRIORITIES -> 400
        assert resp.status_code == 400

    def test_parent_id_as_integer(self, client):
        """Sending parent_id as integer — returns 400."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "parent_id": 1},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_body_as_list(self, client):
        """Sending a JSON array as the body — FastAPI should reject with 422."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            content=b'["not a dict"]',
            headers={"Content-Type": "application/json"},
            params={"token": token},
        )
        assert resp.status_code == 422

    def test_empty_json_body(self, client):
        """Sending empty JSON {} — title is required, should be 400."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_title_as_null(self, client):
        """Sending title as null — should be 400 (title required)."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": None},
            params={"token": token},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Cross-task isolation
# ---------------------------------------------------------------------------


class TestCrossTaskIsolation:
    def _setup(self, client):
        """Create two tasks and one item in task-a. Returns (token, item_id)."""
        _post_task(client, "taskalpha")
        _post_task(client, "taskbeta")
        token = _register(client)
        resp = client.post(
            "/api/tasks/taskalpha/items",
            json={"title": "Alpha item"},
            params={"token": token},
        )
        assert resp.status_code == 201
        return token, resp.json()["id"]

    def test_get_item_wrong_task(self, client):
        """GET item via wrong task should 404."""
        token, item_id = self._setup(client)
        resp = client.get(f"/api/tasks/taskbeta/items/{item_id}")
        assert resp.status_code == 404

    def test_patch_item_wrong_task(self, client):
        """PATCH item via wrong task should 404."""
        token, item_id = self._setup(client)
        resp = client.patch(
            f"/api/tasks/taskbeta/items/{item_id}",
            json={"status": "archived"},
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_delete_item_wrong_task(self, client):
        """DELETE item via wrong task should 404."""
        token, item_id = self._setup(client)
        resp = client.delete(
            f"/api/tasks/taskbeta/items/{item_id}",
            params={"token": token},
        )
        assert resp.status_code == 404

    def test_cross_task_parent(self, client):
        """Creating item in task-b with parent from task-a should 404."""
        token, item_id_a = self._setup(client)
        resp = client.post(
            "/api/tasks/taskbeta/items",
            json={"title": "Beta item", "parent_id": item_id_a},
            params={"token": token},
        )
        # parent must exist in same task -> 404
        assert resp.status_code == 404

    def test_cross_task_comments(self, client):
        """List comments on task-a item via task-b URL should 404."""
        token, item_id = self._setup(client)
        client.post(
            f"/api/tasks/taskalpha/items/{item_id}/comments",
            json={"content": "hello"},
            params={"token": token},
        )
        resp = client.get(f"/api/tasks/taskbeta/items/{item_id}/comments")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 4. Race condition simulation (sequential but rapid)
# ---------------------------------------------------------------------------


class TestRapidSequential:
    def test_200_items_unique_sequential_ids(self, client):
        """Create 200 items sequentially; all IDs must be unique and sequential."""
        _post_task(client)
        token = _register(client)
        ids = []
        for i in range(200):
            resp = client.post(
                "/api/tasks/adv-task/items",
                json={"title": f"Item {i}"},
                params={"token": token},
            )
            assert resp.status_code == 201
            ids.append(resp.json()["id"])
        assert len(set(ids)) == 200
        expected = [f"ADV-{i}" for i in range(1, 201)]
        assert ids == expected


# ---------------------------------------------------------------------------
# 5. Pagination edge cases
# ---------------------------------------------------------------------------


class TestPaginationEdgeCases:
    def _setup_items(self, client, n=5):
        _post_task(client)
        token = _register(client)
        for i in range(n):
            client.post(
                "/api/tasks/adv-task/items",
                json={"title": f"Item {i}"},
                params={"token": token},
            )

    def test_page_zero_clamped(self, client):
        """page=0 should be clamped to 1 and return the first page."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"page": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) > 0

    def test_page_negative(self, client):
        """page=-1 should be clamped to 1 and return the first page."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"page": -1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) > 0

    def test_per_page_zero(self, client):
        """per_page=0 should be clamped to 1 and return 1 item."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"per_page": 0})
        assert resp.status_code == 200
        data = resp.json()
        # clamped to 1, so we get exactly 1 item (and has_next=True since 5 items)
        assert len(data["items"]) == 1

    def test_per_page_101_clamped(self, client):
        """per_page=101 should be clamped to 100."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"per_page": 101})
        assert resp.status_code == 200
        data = resp.json()
        # All 5 items returned (within clamped 100 limit)
        assert len(data["items"]) == 5
        assert data["per_page"] == 100

    def test_per_page_negative(self, client):
        """per_page=-5 should be clamped to 1."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"per_page": -5})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    def test_very_large_page(self, client):
        """page=99999 with only 5 items should return empty list and has_next=False."""
        self._setup_items(client)
        resp = client.get("/api/tasks/adv-task/items", params={"page": 99999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["has_next"] is False


# ---------------------------------------------------------------------------
# 6. Unicode and special characters
# ---------------------------------------------------------------------------


class TestUnicodeAndSpecialChars:
    def test_title_with_emoji(self, client):
        """Title with emoji is stored correctly."""
        _post_task(client)
        token = _register(client)
        title = "Fix bug \U0001f41b in parser"
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": title},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == title

    def test_title_with_cjk(self, client):
        """Title with CJK characters is stored correctly."""
        _post_task(client)
        token = _register(client)
        title = "\u4fee\u590d\u89e3\u6790\u5668\u4e2d\u7684\u9519\u8bef"
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": title},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == title

    def test_title_with_rtl(self, client):
        """Title with Arabic (RTL) text is stored correctly."""
        _post_task(client)
        token = _register(client)
        title = "\u0625\u0635\u0644\u0627\u062d \u062e\u0637\u0623"
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": title},
            params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["title"] == title

    def test_description_with_null_byte(self, client):
        """Description with null byte — returns 400."""
        _post_task(client)
        token = _register(client)
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": "item", "description": "has\x00null"},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_title_with_newlines_and_tabs(self, client):
        """Title with embedded newlines and tabs is stored as-is."""
        _post_task(client)
        token = _register(client)
        title = "title\nwith\nnewlines\tand\ttabs"
        resp = client.post(
            "/api/tasks/adv-task/items",
            json={"title": title},
            params={"token": token},
        )
        # PostgreSQL TEXT accepts newlines/tabs; _validate_fields only checks len and strip
        # strip() removes leading/trailing whitespace but the title has middle whitespace.
        # However "title\nwith..." stripped != "" so title check passes.
        assert resp.status_code in (201, 400)

    def test_comment_very_long_single_line(self, client):
        """Comment with exactly 5000 chars (no newlines) is accepted."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/adv-task/items", json={"title": "item"}, params={"token": token})
        resp = client.post(
            "/api/tasks/adv-task/items/ADV-1/comments",
            json={"content": "x" * 5000},
            params={"token": token},
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# 7. Double operations
# ---------------------------------------------------------------------------


class TestDoubleOperations:
    def test_delete_twice(self, client):
        """Deleting the same item twice — second should 404."""
        _post_task(client)
        token = _register(client)
        client.post("/api/tasks/adv-task/items", json={"title": "item"}, params={"token": token})
        r1 = client.delete("/api/tasks/adv-task/items/ADV-1", params={"token": token})
        assert r1.status_code == 204
        r2 = client.delete("/api/tasks/adv-task/items/ADV-1", params={"token": token})
        assert r2.status_code == 404

    def test_assign_third_agent(self, client):
        """Item assigned to agent-a; agent-b trying to assign should 409."""
        _post_task(client)
        token_a = _register(client, "agent-alpha")
        token_b = _register(client, "agent-beta")
        client.post("/api/tasks/adv-task/items", json={"title": "item"}, params={"token": token_a})
        r1 = client.post("/api/tasks/adv-task/items/ADV-1/assign", params={"token": token_a})
        assert r1.status_code == 200
        r2 = client.post("/api/tasks/adv-task/items/ADV-1/assign", params={"token": token_b})
        assert r2.status_code == 409
