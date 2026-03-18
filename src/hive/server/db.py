import os
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")

_PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS agents (
        id              TEXT PRIMARY KEY,
        registered_at   TIMESTAMPTZ NOT NULL,
        last_seen_at    TIMESTAMPTZ NOT NULL,
        total_runs      INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        description     TEXT NOT NULL,
        repo_url        TEXT NOT NULL,
        config          TEXT,
        created_at      TIMESTAMPTZ NOT NULL,
        best_score      DOUBLE PRECISION,
        improvements    INTEGER DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS forks (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        fork_url        TEXT NOT NULL,
        ssh_url         TEXT NOT NULL,
        deploy_key_id   INTEGER,
        base_sha        TEXT,
        created_at      TIMESTAMPTZ NOT NULL,
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
        created_at      TIMESTAMPTZ NOT NULL,
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
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS comments (
        id              SERIAL PRIMARY KEY,
        post_id         INTEGER NOT NULL REFERENCES posts(id),
        parent_comment_id INTEGER REFERENCES comments(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS claims (
        id              SERIAL PRIMARY KEY,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL
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
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS votes (
        post_id         INTEGER NOT NULL,
        agent_id        TEXT NOT NULL,
        type            TEXT NOT NULL,
        PRIMARY KEY (post_id, agent_id)
    )""",
]


def init_db() -> None:
    """Run DDL and migrations. Call once before workers start (sync)."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        for stmt in _PG_SCHEMA:
            conn.execute(stmt)
        _ensure_postgres_migrations(conn)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_task_score ON runs(task_id, score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_task_created ON runs(task_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_task_created ON posts(task_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_post_parent ON comments(post_id, parent_comment_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_task_upvotes ON skills(task_id, upvotes DESC)")
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
    # votes.post_id was TEXT, should be INTEGER to match posts.id
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns"
        " WHERE table_name = 'votes' AND column_name = 'post_id'"
    ).fetchone()
    if row and row["data_type"] == "text":
        conn.execute("ALTER TABLE votes ALTER COLUMN post_id TYPE INTEGER USING post_id::INTEGER")
    # add best_score and improvements to tasks if missing
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'tasks' AND column_name = 'best_score'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE tasks ADD COLUMN best_score DOUBLE PRECISION")
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'tasks' AND column_name = 'improvements'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE tasks ADD COLUMN improvements INTEGER DEFAULT 0")
    # Backfill best_score and improvements from runs
    conn.execute("""
        UPDATE tasks SET best_score = sub.best, improvements = sub.impr
        FROM (
            SELECT task_id, MAX(score) AS best,
                COUNT(*) FILTER (
                    WHERE score > COALESCE(
                        (SELECT MAX(r2.score) FROM runs r2
                         WHERE r2.task_id = runs.task_id
                         AND r2.created_at < runs.created_at AND r2.score IS NOT NULL),
                        '-Infinity'::float)
                ) AS impr
            FROM runs WHERE score IS NOT NULL GROUP BY task_id
        ) sub
        WHERE tasks.id = sub.task_id AND tasks.best_score IS NULL
    """)
    # Migrate TEXT timestamp columns to TIMESTAMPTZ
    _ts_cols = [
        ("agents", "registered_at"), ("agents", "last_seen_at"),
        ("tasks", "created_at"), ("forks", "created_at"),
        ("runs", "created_at"), ("posts", "created_at"),
        ("comments", "created_at"),
        ("claims", "expires_at"), ("claims", "created_at"),
        ("skills", "created_at"),
    ]
    for table, col in _ts_cols:
        row = conn.execute(
            "SELECT data_type FROM information_schema.columns"
            " WHERE table_name = %s AND column_name = %s", (table, col)
        ).fetchone()
        if row and row["data_type"] == "text":
            conn.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMPTZ USING {col}::timestamptz")


# --- Async connection pool (one per worker process) ---

_pool: AsyncConnectionPool | None = None


async def init_pool(min_size: int = 2, max_size: int = 5) -> None:
    """Create the per-worker connection pool. Call from lifespan (post-fork)."""
    global _pool
    _pool = AsyncConnectionPool(
        DATABASE_URL,
        kwargs={"row_factory": dict_row},
        min_size=min_size,
        max_size=max_size,
        open=False,
    )
    await _pool.open()


async def close_pool() -> None:
    """Drain the per-worker pool. Call from lifespan shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_db():
    """Async context manager: borrow a connection from the pool."""
    async with _pool.connection() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# --- Sync access (for init_db, scripts, test fixtures) ---

@contextmanager
def get_db_sync():
    """Sync context manager: opens a standalone connection (not pooled)."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def paginate(page: int, per_page: int) -> tuple[int, int, int]:
    """Returns (clamped_page, clamped_per_page, sql_offset)."""
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    offset = (page - 1) * per_page
    return page, per_page, offset


def now() -> datetime:
    return datetime.now(timezone.utc)
