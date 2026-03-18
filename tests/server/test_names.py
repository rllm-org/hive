import pytest

from hive.server.db import init_db, get_db, now
from hive.server.names import generate_name


class TestGenerateName:
    def test_returns_adjective_noun(self, _pg_test_url, monkeypatch):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        init_db()
        with get_db() as conn:
            name = generate_name(conn)
        assert "-" in name

    def test_unique(self, _pg_test_url, monkeypatch):
        if _pg_test_url is None:
            pytest.skip("PostgreSQL not available")
        monkeypatch.setattr("hive.server.db.DATABASE_URL", _pg_test_url)
        init_db()
        import psycopg
        with psycopg.connect(_pg_test_url, autocommit=True) as conn:
            conn.execute("TRUNCATE agents RESTART IDENTITY CASCADE")
        names = set()
        with get_db() as conn:
            for _ in range(20):
                n = generate_name(conn)
                conn.execute(
                    "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                    (n, now(), now()),
                )
                names.add(n)
        assert len(names) == 20
