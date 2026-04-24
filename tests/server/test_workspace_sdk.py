"""Workspace DB migration tests."""

import pytest
import psycopg

from hive.server.db import init_db, get_db_sync


class TestWorkspaceSandboxMigration:
    def test_migration_drops_workspace_sdk_session_id(self, monkeypatch, _pg_test_url):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        init_db()
        with psycopg.connect(_pg_test_url, autocommit=True) as c:
            c.execute("ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS sdk_session_id TEXT")
        init_db()
        with get_db_sync() as conn:
            rows = conn.execute(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema = 'public' AND table_name = 'workspaces'"
            ).fetchall()
        names = {r["column_name"] for r in rows}
        assert "sdk_session_id" not in names
        assert "sdk_sandbox_id" in names
        assert "sdk_base_url" in names
