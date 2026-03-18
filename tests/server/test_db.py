import pytest
from hive.server.db import init_db, get_db_sync, now, paginate


@pytest.fixture()
def pg_db(monkeypatch, _pg_test_url):
    """Fresh Postgres DB for db-level tests."""
    if _pg_test_url is None:
        pytest.skip("PostgreSQL not available")
    monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
    init_db()
    import psycopg
    with psycopg.connect(_pg_test_url, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE votes, comments, claims, skills, posts, runs, forks, agents, tasks"
            " RESTART IDENTITY CASCADE"
        )


class TestInitDb:
    def test_creates_tables(self, pg_db):
        with get_db_sync() as conn:
            for t in ("agents", "tasks", "runs", "posts", "comments", "claims", "skills", "votes"):
                conn.execute(f"SELECT COUNT(*) AS cnt FROM {t}")

    def test_idempotent(self, pg_db):
        init_db()  # second call should not raise


class TestGetDb:
    def test_commits_on_success(self, pg_db):
        with get_db_sync() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                ("a", now(), now()),
            )
        with get_db_sync() as conn:
            assert conn.execute("SELECT id FROM agents WHERE id = %s", ("a",)).fetchone()

    def test_rollback_on_error(self, pg_db):
        try:
            with get_db_sync() as conn:
                conn.execute(
                    "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                    ("b", now(), now()),
                )
                raise ValueError("boom")
        except ValueError:
            pass
        with get_db_sync() as conn:
            assert conn.execute("SELECT id FROM agents WHERE id = %s", ("b",)).fetchone() is None


class TestNow:
    def test_returns_utc_datetime(self):
        from datetime import datetime, timezone
        ts = now()
        assert isinstance(ts, datetime)
        assert ts.tzinfo == timezone.utc


class TestPaginate:
    def test_basic(self):
        page, per_page, offset = paginate(2, 10)
        assert page == 2
        assert per_page == 10
        assert offset == 10

    def test_clamps_page_min(self):
        page, _, _ = paginate(0, 10)
        assert page == 1

    def test_clamps_per_page_max(self):
        _, per_page, _ = paginate(1, 200)
        assert per_page == 100

    def test_clamps_per_page_min(self):
        _, per_page, _ = paginate(1, 0)
        assert per_page == 1
