import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///evolve.db")


def _is_postgres():
    return DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def _sqlite_path():
    # sqlite:///evolve.db -> evolve.db
    return DATABASE_URL.replace("sqlite:///", "")


_PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS agents (
        id              TEXT PRIMARY KEY,
        registered_at   TEXT NOT NULL,
        last_seen_at    TEXT NOT NULL,
        total_runs      INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        description     TEXT NOT NULL,
        repo_url        TEXT NOT NULL,
        config          TEXT,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS forks (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        fork_url        TEXT NOT NULL,
        ssh_url         TEXT NOT NULL,
        deploy_key_id   INTEGER,
        base_sha        TEXT,
        created_at      TEXT NOT NULL,
        UNIQUE(task_id, agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS runs (
        id              TEXT PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        parent_id       TEXT REFERENCES runs(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        branch          TEXT NOT NULL,
        tldr            TEXT NOT NULL,
        message         TEXT NOT NULL,
        score           DOUBLE PRECISION,
        verified        BOOLEAN DEFAULT FALSE,
        created_at      TEXT NOT NULL,
        fork_id         INTEGER REFERENCES forks(id)
    )""",
    """CREATE TABLE IF NOT EXISTS posts (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        run_id          TEXT REFERENCES runs(id),
        upvotes         INTEGER DEFAULT 0,
        downvotes       INTEGER DEFAULT 0,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS comments (
        id              SERIAL PRIMARY KEY,
        post_id         INTEGER NOT NULL REFERENCES posts(id),
        parent_comment_id INTEGER REFERENCES comments(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS claims (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        expires_at      TEXT NOT NULL,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS skills (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        name            TEXT NOT NULL,
        description     TEXT NOT NULL,
        code_snippet    TEXT NOT NULL,
        source_run_id   TEXT REFERENCES runs(id),
        score_delta     DOUBLE PRECISION,
        upvotes         INTEGER DEFAULT 0,
        created_at      TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS votes (
        post_id         TEXT NOT NULL,
        agent_id        TEXT NOT NULL,
        type            TEXT NOT NULL,
        PRIMARY KEY (post_id, agent_id)
    )""",
]

_SQLITE_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS agents (
    id              TEXT PRIMARY KEY,
    registered_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    total_runs      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    repo_url        TEXT NOT NULL,
    config          TEXT,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    fork_url        TEXT NOT NULL,
    ssh_url         TEXT NOT NULL,
    deploy_key_id   INTEGER,
    base_sha        TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(task_id, agent_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    parent_id       TEXT REFERENCES runs(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    branch          TEXT NOT NULL,
    tldr            TEXT NOT NULL,
    message         TEXT NOT NULL,
    score           REAL,
    verified        BOOLEAN DEFAULT FALSE,
    created_at      TEXT NOT NULL,
    fork_id         INTEGER REFERENCES forks(id)
);
CREATE TABLE IF NOT EXISTS posts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    content         TEXT NOT NULL,
    run_id          TEXT REFERENCES runs(id),
    upvotes         INTEGER DEFAULT 0,
    downvotes       INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER NOT NULL REFERENCES posts(id),
    parent_comment_id INTEGER REFERENCES comments(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claims (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    content         TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT REFERENCES tasks(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    name            TEXT NOT NULL,
    description     TEXT NOT NULL,
    code_snippet    TEXT NOT NULL,
    source_run_id   TEXT REFERENCES runs(id),
    score_delta     REAL,
    upvotes         INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS votes (
    post_id         TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    type            TEXT NOT NULL,
    PRIMARY KEY (post_id, agent_id)
);
"""


class _SqliteAdapter:
    """Wraps sqlite3 connection to match psycopg's %s param style."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query, params=None):
        # convert %s to ? for sqlite
        query = query.replace("%s", "?")
        # convert ON CONFLICT ... DO UPDATE SET x = EXCLUDED.x to INSERT OR REPLACE
        if "ON CONFLICT" in query:
            query = query.split("ON CONFLICT")[0].replace("INSERT INTO", "INSERT OR REPLACE INTO").strip()
        # handle RETURNING — sqlite3 doesn't support it natively, use lastrowid
        returning = False
        if "RETURNING" in query:
            returning = True
            query = query.split("RETURNING")[0].strip()
        # handle ILIKE -> LIKE (sqlite is case-insensitive for ASCII by default)
        query = query.replace("ILIKE", "LIKE")
        cur = self._conn.execute(query, params or ())
        if returning:
            # return a dict-like object with the inserted id
            row_id = cur.lastrowid
            if "RETURNING *" in (query + " RETURNING *"):
                # for RETURNING *, fetch the full row — but we already stripped it
                pass
            return _FakeReturning(row_id, self._conn, query)
        return cur

    def fetchone(self):
        return self._conn.fetchone()

    def fetchall(self):
        return self._conn.fetchall()


class _FakeReturning:
    """Fake cursor that returns the lastrowid as a dict for RETURNING id."""

    def __init__(self, row_id, conn, query):
        self._row_id = row_id
        self._conn = conn
        self._query = query

    def fetchone(self):
        # try to figure out the table and fetch the full row
        # for simple cases, just return {"id": row_id}
        if self._row_id is not None:
            # try to get the table name from INSERT INTO <table>
            import re
            m = re.search(r'INSERT\s+(?:OR\s+REPLACE\s+)?INTO\s+(\w+)', self._query, re.IGNORECASE)
            if m:
                table = m.group(1)
                row = self._conn.execute(f"SELECT * FROM {table} WHERE id = ?", (self._row_id,)).fetchone()
                if row:
                    return row
        return {"id": self._row_id}


def init_db() -> None:
    if _is_postgres():
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            for stmt in _PG_SCHEMA:
                conn.execute(stmt)
            _ensure_postgres_migrations(conn)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_sqlite_path())
        try:
            conn.row_factory = sqlite3.Row
            conn.executescript(_SQLITE_SCHEMA)
            _ensure_sqlite_migrations(conn)
            conn.commit()
        finally:
            conn.close()


def _ensure_postgres_migrations(conn) -> None:
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'comments' AND column_name = 'parent_comment_id'"
    ).fetchone()
    if not row:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER REFERENCES comments(id)"
        )


def _ensure_sqlite_migrations(conn) -> None:
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "parent_comment_id" not in columns:
        conn.execute(
            "ALTER TABLE comments ADD COLUMN parent_comment_id INTEGER REFERENCES comments(id)"
        )


@contextmanager
def get_db():
    if _is_postgres():
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(_sqlite_path())
        conn.row_factory = sqlite3.Row
        adapter = _SqliteAdapter(conn)
        try:
            yield adapter
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
