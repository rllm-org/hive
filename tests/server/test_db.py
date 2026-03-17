from hive.server.db import init_db, get_db, now


class TestInitDb:
    def test_creates_tables(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
        # verify we can query all tables
        with get_db() as conn:
            for t in ("agents", "tasks", "runs", "posts", "comments", "claims", "skills", "votes"):
                conn.execute(f"SELECT COUNT(*) AS cnt FROM {t}")

    def test_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
        init_db()  # should not raise

    def test_migrates_existing_comments_table(self, tmp_path, monkeypatch):
        import sqlite3

        db_path = tmp_path / "t.db"
        conn = sqlite3.connect(db_path)
        conn.executescript("""
        CREATE TABLE posts (id INTEGER PRIMARY KEY AUTOINCREMENT);
        CREATE TABLE agents (id TEXT PRIMARY KEY, registered_at TEXT, last_seen_at TEXT);
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            agent_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        conn.commit()
        conn.close()

        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{db_path}")
        init_db()

        with get_db() as conn:
            cols = conn.execute("PRAGMA table_info(comments)").fetchall()
            assert any(col["name"] == "parent_comment_id" for col in cols)


class TestGetDb:
    def test_commits_on_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                ("a", now(), now()),
            )
        with get_db() as conn:
            assert conn.execute("SELECT id FROM agents WHERE id = %s", ("a",)).fetchone()

    def test_rollback_on_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr("hive.server.db.DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
        init_db()
        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO agents (id, registered_at, last_seen_at) VALUES (%s, %s, %s)",
                    ("b", now(), now()),
                )
                raise ValueError("boom")
        except ValueError:
            pass
        with get_db() as conn:
            assert conn.execute("SELECT id FROM agents WHERE id = %s", ("b",)).fetchone() is None


class TestNow:
    def test_returns_iso_format(self):
        ts = now()
        assert "T" in ts
