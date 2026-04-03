import psycopg
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


def _reset_public_schema(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _create_legacy_schema(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            """CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                registered_at TIMESTAMPTZ NOT NULL,
                last_seen_at TIMESTAMPTZ NOT NULL,
                total_runs INTEGER DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                repo_url TEXT NOT NULL,
                config TEXT,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE forks (
                id SERIAL PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                fork_url TEXT NOT NULL,
                ssh_url TEXT NOT NULL,
                deploy_key_id INTEGER,
                base_sha TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE(task_id, agent_id)
            )"""
        )
        conn.execute(
            """CREATE TABLE runs (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                parent_id TEXT REFERENCES runs(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                branch TEXT NOT NULL,
                tldr TEXT NOT NULL,
                message TEXT NOT NULL,
                score DOUBLE PRECISION,
                verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL,
                fork_id INTEGER REFERENCES forks(id)
            )"""
        )
        conn.execute(
            """CREATE TABLE posts (
                id SERIAL PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                content TEXT NOT NULL,
                run_id TEXT REFERENCES runs(id),
                upvotes INTEGER DEFAULT 0,
                downvotes INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE comments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL REFERENCES posts(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE claims (
                id SERIAL PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                content TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE skills (
                id SERIAL PRIMARY KEY,
                task_id TEXT REFERENCES tasks(id),
                agent_id TEXT NOT NULL REFERENCES agents(id),
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                code_snippet TEXT NOT NULL,
                source_run_id TEXT REFERENCES runs(id),
                score_delta DOUBLE PRECISION,
                upvotes INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE votes (
                post_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                type TEXT NOT NULL,
                PRIMARY KEY (post_id, agent_id)
            )"""
        )


class TestInitDb:
    def test_creates_tables(self, pg_db):
        with get_db_sync() as conn:
            for t in ("agents", "tasks", "runs", "posts", "comments", "claims", "skills", "votes"):
                conn.execute(f"SELECT COUNT(*) AS cnt FROM {t}")

    def test_idempotent(self, pg_db):
        init_db()  # second call should not raise

    def test_upgrades_legacy_runs_schema_with_verification_columns(self, monkeypatch, _pg_test_url):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        _reset_public_schema(_pg_test_url)
        _create_legacy_schema(_pg_test_url)

        init_db()

        with get_db_sync() as conn:
            columns = conn.execute(
                "SELECT column_name, column_default FROM information_schema.columns"
                " WHERE table_name = 'runs' AND column_name IN"
                " ('valid', 'verification_status', 'verified_score', 'verification_log',"
                "  'verified_at', 'verification_started_at')"
            ).fetchall()
            indexes = conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
                " AND indexname IN ('idx_runs_verification_pending', 'idx_runs_verification_running',"
                "  'idx_runs_task_verified_score')"
            ).fetchall()

        defaults = {row["column_name"]: row["column_default"] for row in columns}
        assert {row["column_name"] for row in columns} == {
            "valid",
            "verification_status",
            "verified_score",
            "verification_log",
            "verified_at",
            "verification_started_at",
        }
        assert "true" in (defaults["valid"] or "").lower()
        assert "none" in (defaults["verification_status"] or "").lower()
        assert {row["indexname"] for row in indexes} == {
            "idx_runs_verification_pending",
            "idx_runs_verification_running",
            "idx_runs_task_verified_score",
        }

    def test_upgrades_votes_and_comments_from_legacy_schema(self, monkeypatch, _pg_test_url):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        _reset_public_schema(_pg_test_url)
        _create_legacy_schema(_pg_test_url)

        init_db()

        with get_db_sync() as conn:
            vote_cols = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns"
                " WHERE table_name = 'votes' AND column_name IN ('target_type', 'target_id')"
            ).fetchall()
            comment_cols = conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_name = 'comments' AND column_name IN ('parent_comment_id', 'upvotes', 'downvotes')"
            ).fetchall()
            pk_cols = conn.execute(
                "SELECT a.attname AS column_name"
                " FROM pg_index i"
                " JOIN pg_class c ON c.oid = i.indrelid"
                " JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)"
                " WHERE c.relname = 'votes' AND i.indisprimary"
                " ORDER BY array_position(i.indkey, a.attnum)"
            ).fetchall()

        assert {(row["column_name"], row["data_type"]) for row in vote_cols} == {
            ("target_id", "integer"),
            ("target_type", "text"),
        }
        assert {row["column_name"] for row in comment_cols} == {
            "parent_comment_id",
            "upvotes",
            "downvotes",
        }
        assert [row["column_name"] for row in pk_cols] == ["target_type", "target_id", "agent_id"]


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
