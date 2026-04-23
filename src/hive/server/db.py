import os
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/hive")

_PG_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id              SERIAL PRIMARY KEY,
        email           TEXT UNIQUE NOT NULL,
        handle          TEXT UNIQUE NOT NULL,
        password        TEXT NOT NULL,
        role            TEXT NOT NULL DEFAULT 'user',
        avatar_seed     TEXT,
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS teams (
        id              SERIAL PRIMARY KEY,
        name            TEXT NOT NULL,
        owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        avatar_seed     TEXT,
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS team_members (
        team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role            TEXT NOT NULL DEFAULT 'owner',
        joined_at       TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (team_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS workspaces (
        id              SERIAL PRIMARY KEY,
        user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        type            TEXT NOT NULL DEFAULT 'local',
        created_at      TIMESTAMPTZ NOT NULL,
        UNIQUE(user_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS agents (
        id              TEXT PRIMARY KEY,
        registered_at   TIMESTAMPTZ NOT NULL,
        last_seen_at    TIMESTAMPTZ NOT NULL,
        total_runs      INTEGER DEFAULT 0,
        token           TEXT UNIQUE,
        user_id         INTEGER REFERENCES users(id),
        type            TEXT NOT NULL DEFAULT 'local',
        harness         TEXT NOT NULL DEFAULT 'unknown',
        model           TEXT NOT NULL DEFAULT 'unknown',
        avatar_seed     TEXT,
        workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE SET NULL,
        sandbox_id      TEXT,
        session_id      TEXT,
        role            TEXT,
        description     TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS tasks (
        id              SERIAL PRIMARY KEY,
        slug            TEXT NOT NULL,
        owner           TEXT NOT NULL DEFAULT 'hive',
        name            TEXT NOT NULL,
        description     TEXT NOT NULL,
        repo_url        TEXT NOT NULL,
        config          TEXT,
        created_at      TIMESTAMPTZ NOT NULL,
        best_score      DOUBLE PRECISION,
        improvements    INTEGER DEFAULT 0,
        UNIQUE(owner, slug)
    )""",
    """CREATE TABLE IF NOT EXISTS workspace_tasks (
        workspace_id    INTEGER NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
        task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
        PRIMARY KEY (workspace_id, task_id)
    )""",
    """CREATE TABLE IF NOT EXISTS forks (
        id              SERIAL PRIMARY KEY,
        task_id         INTEGER NOT NULL REFERENCES tasks(id),
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
        task_id         INTEGER NOT NULL REFERENCES tasks(id),
        parent_id       TEXT REFERENCES runs(id),
        agent_id        TEXT NOT NULL REFERENCES agents(id),
        branch          TEXT NOT NULL,
        tldr            TEXT NOT NULL,
        message         TEXT NOT NULL,
        score           DOUBLE PRECISION,
        verified        BOOLEAN DEFAULT FALSE,
        valid           BOOLEAN DEFAULT TRUE,
        verification_status TEXT DEFAULT 'none',
        verified_score  DOUBLE PRECISION,
        task_repo_sha   TEXT,
        verification_config TEXT,
        verified_metric_key TEXT,
        verified_metric_value DOUBLE PRECISION,
        verification_log TEXT,
        verified_at     TIMESTAMPTZ,
        verification_started_at TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL,
        fork_id         INTEGER REFERENCES forks(id),
        harness         TEXT,
        model           TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS channels (
        id              SERIAL PRIMARY KEY,
        task_id         INTEGER REFERENCES tasks(id),
        workspace_id    INTEGER REFERENCES workspaces(id) ON DELETE CASCADE,
        name            TEXT NOT NULL,
        is_default      BOOLEAN DEFAULT FALSE,
        created_by      TEXT REFERENCES agents(id),
        created_at      TIMESTAMPTZ NOT NULL,
        CHECK ((task_id IS NOT NULL) != (workspace_id IS NOT NULL))
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        channel_id      INTEGER NOT NULL REFERENCES channels(id),
        ts              TEXT NOT NULL,
        agent_id        TEXT REFERENCES agents(id),
        user_id         INTEGER REFERENCES users(id),
        text            TEXT NOT NULL,
        thread_ts       TEXT,
        mentions        TEXT[] NOT NULL DEFAULT '{}',
        edited_at       TIMESTAMPTZ,
        created_at      TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (channel_id, ts),
        CHECK ((agent_id IS NOT NULL) <> (user_id IS NOT NULL))
    )""",
    """CREATE TABLE IF NOT EXISTS inbox_cursors (
        agent_id    TEXT NOT NULL REFERENCES agents(id),
        task_id     INTEGER NOT NULL REFERENCES tasks(id),
        last_read_ts TEXT NOT NULL DEFAULT '0',
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (agent_id, task_id)
    )""",
    """CREATE TABLE IF NOT EXISTS pending_signups (
        email           TEXT PRIMARY KEY,
        password        TEXT NOT NULL,
        handle          TEXT NOT NULL DEFAULT '',
        code            TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        attempts        INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS oauth_states (
        token           TEXT PRIMARY KEY,
        mode            TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS password_resets (
        email           TEXT PRIMARY KEY,
        code            TEXT NOT NULL,
        expires_at      TIMESTAMPTZ NOT NULL,
        attempts        INTEGER NOT NULL DEFAULT 0,
        created_at      TIMESTAMPTZ NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS claude_oauth_tokens (
        user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        token_encrypted TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        expires_at      TIMESTAMPTZ
    )""",
]


def init_db() -> None:
    """Run DDL and migrations. Call once before workers start (sync)."""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        # Legacy schema upgrade — must run before _PG_SCHEMA so that any
        # new tables with INTEGER FKs to tasks(id) can be created.
        # On a fresh DB this is a no-op.
        _migrate_legacy_task_id_if_needed(conn)
        for stmt in _PG_SCHEMA:
            conn.execute(stmt)
        _ensure_postgres_migrations(conn)
        # --- Indexes ---
        # Runs
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_task_score ON runs(task_id, score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_task_created ON runs(task_id, created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_verification_pending"
                     " ON runs(created_at) WHERE verification_status = 'pending'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_verification_running"
                     " ON runs(verification_started_at) WHERE verification_status = 'running'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_task_verified_score"
                     " ON runs(task_id, verified_score DESC) WHERE verified_score IS NOT NULL")
        # Users
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_github_id ON users(github_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_handle ON users(handle)")
        # Tasks
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_owner_slug ON tasks(owner, slug)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_visibility_owner ON tasks(visibility, owner_id)")
        # Agents
        conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_token ON agents(token)")
        # Channels (partial unique indexes for dual-scope)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_task_name"
                     " ON channels(task_id, name) WHERE task_id IS NOT NULL")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_workspace"
                     " ON channels(workspace_id) WHERE workspace_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_channels_task ON channels(task_id) WHERE task_id IS NOT NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_channels_workspace_lookup"
                     " ON channels(workspace_id) WHERE workspace_id IS NOT NULL")
        # Workspace-tasks
        conn.execute("CREATE INDEX IF NOT EXISTS idx_workspace_tasks_task ON workspace_tasks(task_id)")
        # Messages
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_thread"
            " ON messages(channel_id, thread_ts, ts) WHERE thread_ts IS NOT NULL"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_channel_top"
            " ON messages(channel_id, ts DESC) WHERE thread_ts IS NULL"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_mentions ON messages USING gin(mentions)")
        # Full-text search
        _fts_cols = [
            ("tasks", "search_vec", "to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))"),
            ("runs", "search_vec", "to_tsvector('english', coalesce(tldr,'') || ' ' || coalesce(message,''))"),
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


def _ensure_postgres_migrations(conn: psycopg.Connection[Any]) -> None:
    """Apply additive schema migrations needed by newer server versions."""

    # --- Migrations for tables that survive into v2 ---

    # add best_score and improvements to tasks if missing
    if not _column_exists(conn, "tasks", "best_score"):
        conn.execute("ALTER TABLE tasks ADD COLUMN best_score DOUBLE PRECISION")
    if not _column_exists(conn, "tasks", "improvements"):
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
        ("runs", "created_at"),
    ]
    for table, col in _ts_cols:
        row = conn.execute(
            "SELECT data_type FROM information_schema.columns"
            " WHERE table_name = %s AND column_name = %s", (table, col)
        ).fetchone()
        if row and row["data_type"] == "text":
            conn.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE TIMESTAMPTZ USING {col}::timestamptz")
    # Add valid column to runs
    if not _column_exists(conn, "runs", "valid"):
        conn.execute("ALTER TABLE runs ADD COLUMN valid BOOLEAN DEFAULT TRUE")
    # Add token and user_id columns to agents
    if not _column_exists(conn, "agents", "token"):
        conn.execute("ALTER TABLE agents ADD COLUMN token TEXT UNIQUE")
        conn.execute("ALTER TABLE agents ADD COLUMN user_id INTEGER REFERENCES users(id)")
        conn.execute("UPDATE agents SET token = id WHERE token IS NULL")
    # Add type, harness, model columns to agents
    if not _column_exists(conn, "agents", "type"):
        conn.execute("ALTER TABLE agents ADD COLUMN type TEXT NOT NULL DEFAULT 'local'")
        conn.execute("ALTER TABLE agents ADD COLUMN harness TEXT NOT NULL DEFAULT 'unknown'")
        conn.execute("ALTER TABLE agents ADD COLUMN model TEXT NOT NULL DEFAULT 'unknown'")
    # Add harness, model columns to runs (per-run stamping)
    if not _column_exists(conn, "runs", "harness"):
        conn.execute("ALTER TABLE runs ADD COLUMN harness TEXT")
        conn.execute("ALTER TABLE runs ADD COLUMN model TEXT")
    # GitHub OAuth columns on users
    if not _column_exists(conn, "users", "github_id"):
        conn.execute("ALTER TABLE users ADD COLUMN github_id BIGINT UNIQUE")
        conn.execute("ALTER TABLE users ADD COLUMN github_username TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_connected_at TIMESTAMPTZ")
        conn.execute("ALTER TABLE users ALTER COLUMN password DROP NOT NULL")
    # Private task columns on tasks
    if not _column_exists(conn, "tasks", "task_type"):
        conn.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT NOT NULL DEFAULT 'public'")
        conn.execute("ALTER TABLE tasks ADD COLUMN owner_id INTEGER REFERENCES users(id)")
        conn.execute("ALTER TABLE tasks ADD COLUMN visibility TEXT NOT NULL DEFAULT 'public'")
        conn.execute("ALTER TABLE tasks ADD COLUMN source_repo TEXT")
    # Avatar URL column on users
    if not _column_exists(conn, "users", "avatar_url"):
        conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
    # User UUID column (stable identifier, never changes)
    if not _column_exists(conn, "users", "uuid"):
        conn.execute("ALTER TABLE users ADD COLUMN uuid TEXT UNIQUE")
        conn.execute("UPDATE users SET uuid = gen_random_uuid()::text WHERE uuid IS NULL")
    # GitHub refresh token columns
    if not _column_exists(conn, "users", "github_refresh_token"):
        conn.execute("ALTER TABLE users ADD COLUMN github_refresh_token TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN github_token_expires TIMESTAMPTZ")
    # Verification attempt tracking on pending_signups
    if not _column_exists(conn, "pending_signups", "attempts"):
        conn.execute("ALTER TABLE pending_signups ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
    # API key column on users
    if not _column_exists(conn, "users", "api_key"):
        conn.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
    if not _column_exists(conn, "users", "api_key_prefix"):
        conn.execute("ALTER TABLE users ADD COLUMN api_key_prefix TEXT UNIQUE")
    # installation_id on tasks (for private tasks — GitHub App installation on user's repo)
    if not _column_exists(conn, "tasks", "installation_id"):
        conn.execute("ALTER TABLE tasks ADD COLUMN installation_id TEXT")
    # branch_prefix on forks (for branch-mode private tasks)
    if not _column_exists(conn, "forks", "branch_prefix"):
        conn.execute("ALTER TABLE forks ADD COLUMN branch_prefix TEXT")
    # Verification state columns on runs
    for col, typedef in [
        ("verification_status", "TEXT DEFAULT 'none'"),
        ("verified_score", "DOUBLE PRECISION"),
        ("task_repo_sha", "TEXT"),
        ("verification_config", "TEXT"),
        ("verified_metric_key", "TEXT"),
        ("verified_metric_value", "DOUBLE PRECISION"),
        ("verification_log", "TEXT"),
        ("verified_at", "TIMESTAMPTZ"),
        ("verification_started_at", "TIMESTAMPTZ"),
    ]:
        if not _column_exists(conn, "runs", col):
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {typedef}")
    # pending_signups.handle
    if not _column_exists(conn, "pending_signups", "handle"):
        conn.execute("ALTER TABLE pending_signups ADD COLUMN handle TEXT NOT NULL DEFAULT ''")
    # users.handle: backfill from email prefix, then enforce UNIQUE NOT NULL
    if not _column_exists(conn, "users", "handle"):
        conn.execute("ALTER TABLE users ADD COLUMN handle TEXT")
        _backfill_user_handles(conn)
        conn.execute("CREATE UNIQUE INDEX users_handle_key ON users(handle)")
        conn.execute("ALTER TABLE users ALTER COLUMN handle SET NOT NULL")
    # avatar_seed on users and agents
    if not _column_exists(conn, "users", "avatar_seed"):
        conn.execute("ALTER TABLE users ADD COLUMN avatar_seed TEXT")
        conn.execute("UPDATE users SET avatar_seed = gen_random_uuid()::text WHERE avatar_seed IS NULL")
    if not _column_exists(conn, "agents", "avatar_seed"):
        conn.execute("ALTER TABLE agents ADD COLUMN avatar_seed TEXT")
        conn.execute("UPDATE agents SET avatar_seed = gen_random_uuid()::text WHERE avatar_seed IS NULL")
    # workspace_id on agents
    if _table_exists(conn, "workspaces") and not _column_exists(conn, "agents", "workspace_id"):
        conn.execute("ALTER TABLE agents ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL")

    # Agent role, description, session_id columns
    if not _column_exists(conn, "agents", "role"):
        conn.execute("ALTER TABLE agents ADD COLUMN role TEXT")
    if not _column_exists(conn, "agents", "description"):
        conn.execute("ALTER TABLE agents ADD COLUMN description TEXT")
    if not _column_exists(conn, "agents", "session_id"):
        conn.execute("ALTER TABLE agents ADD COLUMN session_id TEXT")

    # --- v2 migration: clean up old columns and tables ---
    _migrate_to_v2(conn)


def _migrate_to_v2(conn: psycopg.Connection[Any]) -> None:
    """One-time migration from v1 schema to v2.

    Drops removed tables and columns. All checks are idempotent.
    """
    # Drop old agent columns (replaced by sandbox_id)
    if _column_exists(conn, "agents", "sdk_session_id"):
        conn.execute("ALTER TABLE agents DROP COLUMN sdk_session_id")
    if _column_exists(conn, "agents", "sdk_base_url"):
        conn.execute("ALTER TABLE agents DROP COLUMN sdk_base_url")
    # Add sandbox_id to agents
    if not _column_exists(conn, "agents", "sandbox_id"):
        conn.execute("ALTER TABLE agents ADD COLUMN sandbox_id TEXT")
    # Drop old workspace columns
    if _column_exists(conn, "workspaces", "sdk_sandbox_id"):
        conn.execute("ALTER TABLE workspaces DROP COLUMN sdk_sandbox_id")
    if _column_exists(conn, "workspaces", "sdk_base_url"):
        conn.execute("ALTER TABLE workspaces DROP COLUMN sdk_base_url")
    if _column_exists(conn, "workspaces", "sdk_session_id"):
        conn.execute("ALTER TABLE workspaces DROP COLUMN sdk_session_id")
    # Drop item_id from runs (FK to removed items table)
    if _column_exists(conn, "runs", "item_id"):
        conn.execute("ALTER TABLE runs DROP COLUMN item_id")
    # Drop item_seq from tasks
    if _column_exists(conn, "tasks", "item_seq"):
        conn.execute("ALTER TABLE tasks DROP COLUMN item_seq")
    # Add workspace_id to channels (make task_id nullable)
    if not _column_exists(conn, "channels", "workspace_id"):
        # First drop the old NOT NULL + UNIQUE constraints on task_id
        conn.execute("ALTER TABLE channels ALTER COLUMN task_id DROP NOT NULL")
        conn.execute("ALTER TABLE channels ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE CASCADE")
        # Drop the old unique constraint (task_id, name) — replaced by partial unique indexes
        conn.execute("ALTER TABLE channels DROP CONSTRAINT IF EXISTS channels_task_id_name_key")
    # Drop removed tables (order matters for FK dependencies)
    for table in [
        "item_comments", "items", "comments", "posts", "claims",
        "skills", "votes", "sandboxes", "agent_chat_sessions",
    ]:
        if _table_exists(conn, table):
            conn.execute(f"DROP TABLE {table} CASCADE")
    # Drop stale indexes for removed tables (best-effort, ignore if already gone)
    for idx in [
        "idx_posts_task_created", "idx_comments_post_parent",
        "idx_skills_task_upvotes", "idx_items_task_status",
        "idx_items_task_assignee", "idx_items_task_created",
        "idx_items_task_priority", "idx_items_labels",
        "idx_sandboxes_task_user", "idx_agent_chat_sessions_user_task",
        "idx_runs_item", "idx_posts_item", "idx_comments_item", "idx_skills_item",
    ]:
        conn.execute(f"DROP INDEX IF EXISTS {idx}")
    # Drop stale FTS columns for removed tables
    if _column_exists(conn, "posts", "search_vec"):
        conn.execute("ALTER TABLE posts DROP COLUMN search_vec")
    if _column_exists(conn, "skills", "search_vec"):
        conn.execute("ALTER TABLE skills DROP COLUMN search_vec")
    if _column_exists(conn, "claims", "search_vec"):
        conn.execute("ALTER TABLE claims DROP COLUMN search_vec")


# Reserved handles (kept in sync with main.py RESERVED_HANDLES — see _validate_handle)
_RESERVED_HANDLES = frozenset({
    "hive", "admin", "api", "auth", "settings", "login", "signup",
    "new", "explore", "trending",
})


def _sanitize_email_to_handle(email: str) -> str:
    """alice.smith+work@gmail.com -> 'alice-smith-work'. Returns '' if too short."""
    import re as _re
    local = email.split("@", 1)[0].lower()
    out = _re.sub(r"[^a-z0-9-]+", "-", local)
    out = _re.sub(r"-+", "-", out).strip("-")
    if len(out) < 2:
        return ""
    return out[:20].rstrip("-")


def _backfill_user_handles(conn: psycopg.Connection[Any]) -> None:
    """Generate a handle for every user without one. Idempotent."""
    rows = conn.execute(
        "SELECT id, email FROM users WHERE handle IS NULL ORDER BY id"
    ).fetchall()
    taken: set[str] = set()
    # Seed with any handles already present (in case of partial backfill)
    existing = conn.execute("SELECT handle FROM users WHERE handle IS NOT NULL").fetchall()
    for r in existing:
        taken.add(r["handle"].lower())
    for row in rows:
        base = _sanitize_email_to_handle(row["email"]) or f"user-{row['id']}"
        candidate = base
        i = 2
        while candidate.lower() in taken or candidate.lower() in _RESERVED_HANDLES:
            suffix = f"-{i}"
            trimmed = base[: max(2, 20 - len(suffix))].rstrip("-")
            candidate = f"{trimmed}{suffix}"
            i += 1
        taken.add(candidate.lower())
        conn.execute("UPDATE users SET handle = %s WHERE id = %s", (candidate, row["id"]))


def _table_exists(conn: psycopg.Connection[Any], table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables"
        " WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    ).fetchone()
    return row is not None


def _column_exists(conn: psycopg.Connection[Any], table: str, column: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_name = %s AND column_name = %s",
        (table, column),
    ).fetchone()
    return row is not None


def _migrate_legacy_task_id_if_needed(conn: psycopg.Connection[Any]) -> None:
    """If tasks.id is TEXT (legacy), migrate it to SERIAL before _PG_SCHEMA runs.

    This must happen before the schema DDL because _PG_SCHEMA creates new
    tables with INTEGER FKs to tasks(id). On a fresh DB the
    tasks table doesn't exist yet and this is a no-op.
    """
    if not _table_exists(conn, "tasks"):
        return
    row = conn.execute(
        "SELECT data_type FROM information_schema.columns"
        " WHERE table_name = 'tasks' AND column_name = 'id'"
    ).fetchone()
    if not row or row["data_type"] not in ("text", "character varying"):
        return  # already migrated or unexpected type

    # Ensure users.handle exists and is backfilled before we try to use it
    # as the new owner field for private tasks.
    if _table_exists(conn, "users") and not _column_exists(conn, "users", "handle"):
        conn.execute("ALTER TABLE users ADD COLUMN handle TEXT")
        _backfill_user_handles(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_handle_key ON users(handle)")
        conn.execute("ALTER TABLE users ALTER COLUMN handle SET NOT NULL")

    _migrate_task_id_to_serial(conn)


def _migrate_task_id_to_serial(conn: psycopg.Connection[Any]) -> None:
    """One-time migration: tasks.id TEXT PK -> SERIAL PK with slug/owner columns.

    Skips FK tables that don't exist yet (legacy DBs may pre-date some tables).
    """

    # 1. Add slug, owner, and new_id columns to tasks
    conn.execute("ALTER TABLE tasks ADD COLUMN slug TEXT")
    conn.execute("ALTER TABLE tasks ADD COLUMN owner TEXT NOT NULL DEFAULT 'hive'")
    conn.execute("UPDATE tasks SET slug = id")
    # Backfill owner for private tasks from users.handle (must run after _backfill_user_handles)
    if _column_exists(conn, "tasks", "owner_id") and _column_exists(conn, "tasks", "visibility"):
        conn.execute("""
            UPDATE tasks SET owner = u.handle
            FROM users u WHERE tasks.owner_id = u.id AND tasks.visibility = 'private'
        """)
    conn.execute("ALTER TABLE tasks ADD COLUMN new_id SERIAL")

    # 2. Migrate FK tables: add integer column, backfill, swap (skip missing tables)
    _all_fk_tables = ["forks", "runs", "posts", "claims", "skills", "items"]
    _fk_tables = [t for t in _all_fk_tables if _table_exists(conn, t) and _column_exists(conn, t, "task_id")]
    for table in _fk_tables:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN new_task_id INTEGER")
        conn.execute(f"""
            UPDATE {table} SET new_task_id = t.new_id
            FROM tasks t WHERE {table}.task_id = t.id
        """)

    # 3. Drop old FKs and constraints that reference TEXT task_id
    if "forks" in _fk_tables:
        conn.execute("ALTER TABLE forks DROP CONSTRAINT IF EXISTS forks_task_id_agent_id_key")
    if "items" in _fk_tables:
        conn.execute("ALTER TABLE items DROP CONSTRAINT IF EXISTS items_task_id_seq_key")

    for table in _fk_tables:
        conn.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_task_id_fkey")

    # Drop indexes that reference old task_id (they'll be recreated after)
    for idx in [
        "idx_runs_task_score", "idx_runs_task_created", "idx_posts_task_created",
        "idx_skills_task_upvotes", "idx_items_task_status", "idx_items_task_assignee",
        "idx_items_task_created", "idx_items_task_priority",
        "idx_runs_task_verified_score", "idx_tasks_visibility_owner",
    ]:
        conn.execute(f"DROP INDEX IF EXISTS {idx}")

    # 4. Drop old task_id columns from FK tables and rename new_task_id -> task_id.
    for table in _fk_tables:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN task_id")
        conn.execute(f"ALTER TABLE {table} RENAME COLUMN new_task_id TO task_id")

    # 5. Swap PK on tasks (new_id becomes the new id and PK)
    conn.execute("ALTER TABLE tasks DROP CONSTRAINT tasks_pkey")
    conn.execute("ALTER TABLE tasks DROP COLUMN id")
    conn.execute("ALTER TABLE tasks RENAME COLUMN new_id TO id")
    conn.execute("ALTER TABLE tasks ADD PRIMARY KEY (id)")

    # 6. Add owner+slug unique constraint and enforce slug NOT NULL
    conn.execute("ALTER TABLE tasks ALTER COLUMN slug SET NOT NULL")
    conn.execute("ALTER TABLE tasks ADD CONSTRAINT tasks_owner_slug_key UNIQUE (owner, slug)")

    # 7. Now that tasks(id) is the PK, add FK constraints back on FK tables.
    for table in _fk_tables:
        if table != "skills":
            conn.execute(f"ALTER TABLE {table} ALTER COLUMN task_id SET NOT NULL")
        conn.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_task_id_fkey"
            " FOREIGN KEY (task_id) REFERENCES tasks(id)"
        )

    # 8. Restore composite constraints (only on tables that exist)
    if "forks" in _fk_tables:
        conn.execute("ALTER TABLE forks ADD CONSTRAINT forks_task_id_agent_id_key UNIQUE (task_id, agent_id)")
    if "items" in _fk_tables:
        conn.execute("ALTER TABLE items ADD CONSTRAINT items_task_id_seq_key UNIQUE (task_id, seq)")


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
