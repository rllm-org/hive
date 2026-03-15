import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = os.environ.get("HIVE_DB_PATH", "evolve.db")

_SCHEMA = """
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
    created_at      TEXT NOT NULL
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


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(_SCHEMA)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()
