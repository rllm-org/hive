from hive.server.db import init_db, get_db, now
from hive.server.names import generate_name


class TestGenerateName:
    def test_returns_adjective_noun(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
        with get_db() as conn:
            name = generate_name(conn)
        assert "-" in name

    def test_unique(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
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
