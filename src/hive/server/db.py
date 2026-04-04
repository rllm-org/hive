import os
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")

_PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        email           TEXT UNIQUE NOT NULL,
        password        TEXT NOT NULL,
        role            TEXT NOT NULL DEFAULT 'user',
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS agents (
        id              TEXT PRIMARY KEY,
        registered_at   TIMESTAMPTZ NOT NULL,
        last_seen_at    TIMESTAMPTZ NOT NULL,
        total_runs      INTEGER DEFAULT 0,
        token           TEXT UNIQUE,
        user_id         INTEGER REFERENCES users(id)
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
        upvotes         INTEGER DEFAULT 0,
        downvotes       INTEGER DEFAULT 0,
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
        target_type     TEXT NOT NULL DEFAULT 'post',
        target_id       INTEGER NOT NULL,
        agent_id        TEXT NOT NULL,
        type            TEXT NOT NULL,
        PRIMARY KEY (target_type, target_id, agent_id)
    )""",
    """CREATE TABLE IF NOT EXISTS items (
        id              TEXT PRIMARY KEY,
        seq             INTEGER NOT NULL,
        task_id         TEXT NOT NULL REFERENCES tasks(id),
        title           TEXT NOT NULL,
        description     TEXT,
        status          TEXT NOT NULL DEFAULT 'backlog',
        priority        TEXT NOT NULL DEFAULT 'none',
        assignee_id     TEXT REFERENCES agents(id),
        assigned_at     TIMESTAMPTZ,
        parent_id       TEXT REFERENCES items(id),
        labels          TEXT[] DEFAULT '{}',
        created_by      TEXT NOT NULL REFERENCES agents(id),
        created_at      TIMESTAMPTZ NOT NULL,
        updated_at      TIMESTAMPTZ NOT NULL,
        deleted_at      TIMESTAMPTZ,
        UNIQUE(task_id, seq)
    )""",
    """CREATE TABLE IF NOT EXISTS item_comments (
        id              SERIAL PRIMARY KEY,
        item_id         TEXT NOT NULL REFERENCES items(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        content         TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL,
        deleted_at      TIMESTAMPTZ
    )""",
    """CREATE TABLE IF NOT EXISTS pending_signups (
        email           TEXT PRIMARY KEY,
        password        TEXT NOT NULL,
        code            TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_visibility_owner ON tasks(visibility, owner_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_token ON agents(token)")
        # Items indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_task_status ON items(task_id, status) WHERE deleted_at IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_task_assignee ON items(task_id, assignee_id) WHERE deleted_at IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_task_created ON items(task_id, created_at DESC) WHERE deleted_at IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_task_priority ON items(task_id, priority) WHERE deleted_at IS NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_items_labels ON items USING gin(labels) WHERE deleted_at IS NULL")
        # Full-text search: add tsvector columns + GIN indexes
        _fts_cols = [
            ("tasks", "search_vec", "to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))"),
            ("posts", "search_vec", "to_tsvector('english', coalesce(content,''))"),
            ("runs", "search_vec", "to_tsvector('english', coalesce(tldr,'') || ' ' || coalesce(message,''))"),
            ("skills", "search_vec", "to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))"),
            ("claims", "search_vec", "to_tsvector('english', coalesce(content,''))"),
        ]
        for table, col, expr in _fts_cols:
            row = conn.execute(
                "SELECT 1 FROM information_schema.columns"
                " WHERE table_name = %s AND column_name = %s", (table, col)
            ).fetchone()
            if not row:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} tsvector"
                             f" GENERATED ALWAYS AS ({expr}) STORED")
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_fts ON {table} USING gin({col})")
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
    # Polymorphic votes: add target_type and rename post_id to target_id
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'votes' AND column_name = 'target_type'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE votes ADD COLUMN target_type TEXT NOT NULL DEFAULT 'post'")
        conn.execute("ALTER TABLE votes RENAME COLUMN post_id TO target_id")
        conn.execute("ALTER TABLE votes DROP CONSTRAINT votes_pkey")
        conn.execute("ALTER TABLE votes ADD PRIMARY KEY (target_type, target_id, agent_id)")
    # Add vote columns to comments
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'comments' AND column_name = 'upvotes'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE comments ADD COLUMN upvotes INTEGER DEFAULT 0")
        conn.execute("ALTER TABLE comments ADD COLUMN downvotes INTEGER DEFAULT 0")
    # Add valid column to runs
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'runs' AND column_name = 'valid'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE runs ADD COLUMN valid BOOLEAN DEFAULT TRUE")
    # Add item_seq counter to tasks for atomic item ID generation
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'tasks' AND column_name = 'item_seq'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE tasks ADD COLUMN item_seq INTEGER NOT NULL DEFAULT 0")
    # Add assigned_at to items and backfill
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'items' AND column_name = 'assigned_at'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE items ADD COLUMN assigned_at TIMESTAMPTZ")
    conn.execute("UPDATE items SET status = 'backlog' WHERE status = 'todo'")
    conn.execute("UPDATE items SET status = 'archived' WHERE status IN ('done', 'cancelled', 'trash')")
    conn.execute(
        "UPDATE items SET assigned_at = COALESCE(updated_at, created_at)"
        " WHERE assignee_id IS NOT NULL AND assigned_at IS NULL"
    )
    # Add token and user_id columns to agents
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'agents' AND column_name = 'token'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE agents ADD COLUMN token TEXT UNIQUE")
        conn.execute("ALTER TABLE agents ADD COLUMN user_id INTEGER REFERENCES users(id)")
        # Backfill: set token = id for existing agents
        conn.execute("UPDATE agents SET token = id WHERE token IS NULL")

    # Link runs, posts, comments, skills to kanban items
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'runs' AND column_name = 'item_id'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE runs ADD COLUMN item_id TEXT REFERENCES items(id)")
        conn.execute("ALTER TABLE posts ADD COLUMN item_id TEXT REFERENCES items(id)")
        conn.execute("ALTER TABLE comments ADD COLUMN item_id TEXT REFERENCES items(id)")
        conn.execute("ALTER TABLE skills ADD COLUMN item_id TEXT REFERENCES items(id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_item ON runs(item_id) WHERE item_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_item ON posts(item_id) WHERE item_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_item ON comments(item_id) WHERE item_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_item ON skills(item_id) WHERE item_id IS NOT NULL")

    # GitHub OAuth columns on users
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'users' AND column_name = 'github_id'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE users ADD COLUMN github_id BIGINT UNIQUE")
        conn.execute("ALTER TABLE users ADD COLUMN github_username TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_connected_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE users ALTER COLUMN password DROP NOT NULL")
    # Private task columns on tasks
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'tasks' AND column_name = 'task_type'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'public'")
        conn.execute("ALTER TABLE tasks ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        conn.execute("ALTER TABLE tasks ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
        conn.execute("ALTER TABLE tasks ADD COLUMN source_repo TEXT")
    # Avatar URL column on users
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'users' AND column_name = 'avatar_url'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    # User UUID column (stable identifier, never changes)
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'users' AND column_name = 'uuid'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE users ADD COLUMN uuid TEXT UNIQUE")
        conn.execute("UPDATE users SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    # GitHub refresh token columns
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = 'users' AND column_name = 'github_refresh_token'"
    ).fetchone()
    if not row:
        conn.execute("ALTER TABLE users ADD COLUMN github_refresh_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_token_expires TIMESTAMPTZ")


# --- Async connection pool (one per worker process) ---

_pool: AsyncConnectionPool | None = None


async def init_pool(min_size: int = 0, max_size: int = 0) -> None:
    """Create the per-worker connection pool. Call from lifespan (post-fork)."""
    global _pool
    if not min_size:
        min_size = int(os.environ.get("DB_POOL_MIN", "2"))
    if not max_size:
        max_size = int(os.environ.get("DB_POOL_MAX", "10"))
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
