# Items API — Design Spec

Task-scoped item tracking for AI agent coordination. Extends the Hive server with mutable work items (issues/tickets/tasks) and comments, exposed as REST endpoints.

Inspired by Linear's issue model, simplified for agent use.

---

## Scope

- **Items**: mutable work items with status, priority, assignee, labels, subtasks
- **Comments**: flat discussion on items
- **Extension**: new tables + endpoints added to existing Hive FastAPI server
- **Auth**: existing `?token=<agent_id>` mechanism

Not in scope: cycles/sprints, projects, documents, notifications, webhooks, views.

---

## Data Model

### `items`

```sql
CREATE TABLE items (
    id              TEXT PRIMARY KEY,        -- "GSM-1", "GSM-2" (task prefix + sequence)
    seq             INTEGER NOT NULL,        -- numeric part of ID, per-task sequence
    task_id         TEXT NOT NULL REFERENCES tasks(id),
    title           TEXT NOT NULL,
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'backlog',
    priority        TEXT NOT NULL DEFAULT 'none',
    assignee_id     TEXT REFERENCES agents(id),
    parent_id       TEXT REFERENCES items(id),
    labels          TEXT[] DEFAULT '{}',
    created_by      TEXT NOT NULL REFERENCES agents(id),
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    deleted_at      TIMESTAMPTZ,             -- soft delete, null = active
    UNIQUE(task_id, seq)
);

CREATE INDEX idx_items_task_status ON items(task_id, status) WHERE deleted_at IS NULL;
CREATE INDEX idx_items_task_assignee ON items(task_id, assignee_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_items_task_created ON items(task_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_items_task_priority ON items(task_id, priority) WHERE deleted_at IS NULL;
CREATE INDEX idx_items_labels ON items USING gin(labels) WHERE deleted_at IS NULL;
```

**Status values**: `backlog`, `todo`, `in_progress`, `done`, `cancelled`

**Priority values**: `none`, `urgent`, `high`, `medium`, `low`

**ID format**: `{TASK_PREFIX}-{N}` where prefix is derived from `task_id` (uppercase, truncated) and N is a per-task auto-incrementing sequence. Example: task `gsm8k-solver` produces IDs `GSM-1`, `GSM-2`, etc. The `seq` column is internal — not exposed in API responses.

**Subtasks**: set `parent_id` to another item's ID within the same task. Max depth enforced at 5 levels. Cycle detection on PATCH: before updating `parent_id`, walk the parent chain and reject if the item would become its own ancestor.

**Labels**: string array restricted to `[a-zA-Z0-9_-]` characters. No label registry — agents use whatever strings they want within that charset.

**Status transitions**: no enforced workflow. Agents can set any status at any time.

**Soft delete**: `deleted_at` is set on delete. All queries filter `WHERE deleted_at IS NULL`. Soft-deleted items are excluded from all list/detail/context endpoints. Aligns with Hive's "nothing is discarded" principle.

### `item_comments`

```sql
CREATE TABLE item_comments (
    id              SERIAL PRIMARY KEY,
    item_id         TEXT NOT NULL REFERENCES items(id),
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    deleted_at      TIMESTAMPTZ              -- soft delete
);
```

Flat comments (no threading). Each comment belongs to one item. Soft-deleted via `deleted_at`.

### Tasks table change

Add a sequence counter column to the existing `tasks` table:

```sql
ALTER TABLE tasks ADD COLUMN item_seq INTEGER NOT NULL DEFAULT 0;
```

This counter is atomically incremented on each item creation to generate race-safe IDs.

---

## API Endpoints

All endpoints are under `/tasks/{task_id}/items`. Auth via `?token=<agent_id>`.

All queries filter out soft-deleted records (`deleted_at IS NULL`) by default.

### `POST /tasks/{task_id}/items`

Create an item. `id` is auto-generated.

```
Request:
{
  "title": "Fix eval script timeout",
  "description": "eval.sh hangs on large inputs. Add a 60s timeout.",
  "status": "todo",                    // optional, default "backlog"
  "priority": "high",                  // optional, default "none"
  "assignee_id": "swift-phoenix",      // optional
  "parent_id": "GSM-1",               // optional
  "labels": ["bug", "eval"]           // optional, default []
}

Response: 201
{
  "id": "GSM-3",
  "task_id": "gsm8k-solver",
  "title": "Fix eval script timeout",
  "description": "eval.sh hangs on large inputs. Add a 60s timeout.",
  "status": "todo",
  "priority": "high",
  "assignee_id": "swift-phoenix",
  "parent_id": "GSM-1",
  "labels": ["bug", "eval"],
  "created_by": "swift-phoenix",
  "comment_count": 0,
  "created_at": "2026-04-01T10:00:00Z",
  "updated_at": "2026-04-01T10:00:00Z"
}
```

### `POST /tasks/{task_id}/items/bulk`

Create multiple items in one request. Max 50 items per call.

```
Request:
{
  "items": [
    { "title": "Fix timeout", "status": "todo", "priority": "high", "labels": ["bug"] },
    { "title": "Add retries", "status": "backlog", "labels": ["feature"] },
    { "title": "Update docs", "parent_id": "GSM-1" }
  ]
}

Response: 201
{
  "items": [
    { "id": "GSM-3", "title": "Fix timeout", "status": "todo", ... },
    { "id": "GSM-4", "title": "Add retries", "status": "backlog", ... },
    { "id": "GSM-5", "title": "Update docs", "status": "backlog", ... }
  ]
}
```

All items are created in a single transaction. If any item fails validation, the entire batch is rejected.

### `PATCH /tasks/{task_id}/items/bulk`

Update multiple items in one request. Max 50 items per call.

```
Request:
{
  "items": [
    { "id": "GSM-3", "status": "done" },
    { "id": "GSM-4", "status": "in_progress", "assignee_id": "swift-phoenix" }
  ]
}

Response: 200
{
  "items": [
    { "id": "GSM-3", "status": "done", ... },
    { "id": "GSM-4", "status": "in_progress", "assignee_id": "swift-phoenix", ... }
  ]
}
```

### `GET /tasks/{task_id}/items`

List items with filtering and pagination.

```
Query:
  ?status=todo                         // filter by status
  ?status=!done                        // negation: exclude done items
  ?priority=high
  ?assignee=swift-phoenix              // filter by assignee
  ?assignee=none                       // unassigned items only
  ?label=bug                           // items with this label
  ?parent=GSM-1                        // list subtasks of an item
  ?sort=recent|priority|updated        // default: recent (created_at desc)
  ?page=1&per_page=20

Response: 200
{
  "items": [
    {
      "id": "GSM-3",
      "task_id": "gsm8k-solver",
      "title": "Fix eval script timeout",
      "description": "eval.sh hangs on large inputs. Add a 60s timeout.",
      "status": "todo",
      "priority": "high",
      "assignee_id": "swift-phoenix",
      "parent_id": "GSM-1",
      "labels": ["bug", "eval"],
      "created_by": "swift-phoenix",
      "comment_count": 2,
      "created_at": "...",
      "updated_at": "..."
    }
  ],
  "page": 1,
  "per_page": 20,
  "has_next": false
}
```

Sort keys use semantic aliases consistent with existing Hive endpoints:
- `recent` — `created_at DESC` (default)
- `updated` — `updated_at DESC`
- `priority` — `priority ASC` (urgent first)

Append `:asc` or `:desc` to override direction (e.g., `?sort=priority:desc`).

List response includes all fields including `description` — consistent with existing Hive list endpoints (runs, feed, skills).

### `GET /tasks/{task_id}/items/{item_id}`

Full item detail including children.

```
Response: 200
{
  "id": "GSM-3",
  "task_id": "gsm8k-solver",
  "title": "Fix eval script timeout",
  "description": "eval.sh hangs on large inputs. Add a 60s timeout.",
  "status": "todo",
  "priority": "high",
  "assignee_id": "swift-phoenix",
  "parent_id": "GSM-1",
  "labels": ["bug", "eval"],
  "created_by": "swift-phoenix",
  "comment_count": 2,
  "children": [
    { "id": "GSM-4", "title": "Add timeout flag to eval.sh", "status": "backlog" }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

Detail adds `children` (direct subtasks, non-deleted only).

### `PATCH /tasks/{task_id}/items/{item_id}`

Update any mutable field. Only include fields to change.

```
Request:
{
  "status": "in_progress",
  "assignee_id": "quiet-atlas"
}

Response: 200
{
  "id": "GSM-3",
  ...full item with updated fields...
  "updated_at": "2026-04-01T11:00:00Z"
}
```

Updatable fields: `title`, `description`, `status`, `priority`, `assignee_id`, `parent_id`, `labels`.

`updated_at` is set automatically on every PATCH.

**Authorization**: any authenticated agent can update any item. This matches Hive's collaborative model where agents work as a team on shared tasks.

### `POST /tasks/{task_id}/items/{item_id}/assign`

Atomic claim-and-assign. Sets `assignee_id` only if the item is currently unassigned. Prevents race conditions in swarms where multiple agents try to claim the same work.

```
Request: (no body, agent_id from token)

Response: 200
{
  "id": "GSM-3",
  ...full item with assignee_id set to requesting agent...
  "assignee_id": "swift-phoenix",
  "updated_at": "..."
}
```

Returns 409 (Conflict) if the item is already assigned to another agent.

### `DELETE /tasks/{task_id}/items/{item_id}`

Soft delete. Sets `deleted_at` on the item and all its comments. Item is excluded from all future queries.

```
Response: 204 (no body)
```

Returns 409 (Conflict) if the item has non-deleted children (subtasks). Delete children first.

**Authorization**: only the item's `created_by` agent can delete it. Returns 403 otherwise.

---

### `POST /tasks/{task_id}/items/{item_id}/comments`

Add a comment.

```
Request:
{ "content": "Timeout should be configurable via env var" }

Response: 201
{
  "id": 15,
  "item_id": "GSM-3",
  "agent_id": "quiet-atlas",
  "content": "Timeout should be configurable via env var",
  "created_at": "2026-04-01T11:30:00Z"
}
```

### `GET /tasks/{task_id}/items/{item_id}/comments`

List comments, paginated, chronological.

```
Query: ?page=1&per_page=30

Response: 200
{
  "comments": [
    {
      "id": 15,
      "item_id": "GSM-3",
      "agent_id": "quiet-atlas",
      "content": "Timeout should be configurable via env var",
      "created_at": "..."
    }
  ],
  "page": 1,
  "per_page": 30,
  "has_next": false
}
```

### `DELETE /tasks/{task_id}/items/{item_id}/comments/{comment_id}`

Soft delete a comment. Sets `deleted_at`.

```
Response: 204 (no body)
```

**Authorization**: only the comment's `agent_id` (author) can delete it. Returns 403 otherwise.

---

## Implementation

### Files to add/modify

```
src/hive/server/main.py       — register new routes
src/hive/server/db.py          — add items + item_comments tables, queries
src/hive/server/migrate.py     — add migration for new tables + tasks.item_seq column
tests/test_items.py            — endpoint tests
docs/api.md                    — add Items section
```

### ID generation

Atomic counter on the `tasks` table. On item creation:

```sql
UPDATE tasks SET item_seq = item_seq + 1 WHERE id = $1 RETURNING item_seq;
```

This runs inside the same transaction as the INSERT into `items`. The `UPDATE ... RETURNING` is atomic — concurrent transactions serialize on the row lock. The returned value becomes `seq`, and the ID is `{PREFIX}-{seq}`.

Prefix derived by uppercasing the first segment of `task_id` before the first hyphen (e.g., `gsm8k-solver` -> `GSM`). Backed by a `UNIQUE(task_id, seq)` constraint as a safety net.

### Cycle detection

On PATCH when `parent_id` changes:

```python
def has_cycle(item_id, new_parent_id):
    """Walk parent chain from new_parent_id. Reject if item_id is found."""
    current = new_parent_id
    depth = 0
    while current is not None and depth < 5:
        if current == item_id:
            return True  # cycle detected
        current = get_parent(current)
        depth += 1
    if depth >= 5:
        return True  # max depth exceeded
    return False
```

Returns 400 if a cycle would be created or max depth (5) exceeded.

### Validation

- `status` must be one of: `backlog`, `todo`, `in_progress`, `done`, `cancelled`
- `priority` must be one of: `none`, `urgent`, `high`, `medium`, `low`
- `assignee_id` must reference an existing agent
- `parent_id` must reference an existing non-deleted item in the same task
- `labels` max 20 entries, each max 50 chars, chars restricted to `[a-zA-Z0-9_-]`
- `title` max 500 chars
- `description` max 10000 chars
- `content` (comment) max 5000 chars
- Bulk endpoints max 50 items per request
