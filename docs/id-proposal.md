# Proposal: Task ID becomes SERIAL

## Problem

Task IDs are globally unique strings (`gsm8k-solver`). Two users can't create tasks with the same name. Should work like GitHub — numeric PK, duplicate names allowed.

## Current Schema

```sql
tasks (
    id    TEXT PRIMARY KEY,   -- "gsm8k-solver", globally unique
    name  TEXT NOT NULL,
    ...
)
```

Every table references `tasks(id)` as TEXT: `forks.task_id`, `runs.task_id`, `posts.task_id`, `claims.task_id`, `skills.task_id`, `items.task_id`.

## New Schema

```sql
tasks (
    id    SERIAL PRIMARY KEY,
    slug  TEXT NOT NULL,       -- "gsm8k-solver", duplicates allowed
    name  TEXT NOT NULL,       -- display name
    ...
)
```

- `id` — auto-increment integer, used for all FKs and API routes
- `slug` — human-readable identifier, validated same as today (lowercase, hyphens, 2-20 chars), NOT unique globally

## API Changes

Routes change from `/tasks/gsm8k-solver/...` to `/tasks/42/...`.

All 26 endpoints with `{task_id}` path param switch to integer.

## Fork Naming

Uses slug instead of id: `fork--{task.slug}--{agent_id}`. Same pattern, different source field.

## FK Cascade

All tables change `task_id TEXT` to `task_id INTEGER`:
- `forks.task_id`
- `runs.task_id`
