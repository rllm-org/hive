# Model Selector — Design Spec
Date: 2026-04-21

## Summary

Add a model selector pill to the right side of the agent tabs row in the workspace chat panel. Clicking it opens a dropdown to switch the active agent's model mid-session via the agent-sdk config API.

## Architecture

Three touch points, no new files:

1. **`use-workspace-agent.ts`** — expose `setModel(agentId, model)` alongside `sendMessage`/`cancel`
2. **`AgentTabs` in `page.tsx`** — accept `activeModel` and `onModelChange` props; render the pill + dropdown
3. **`page.tsx`** — wire `setModel` from the hook into `handleModelChange`, pass `activeAgent.model` down

## Data Flow

```
User clicks pill → dropdown opens (local state)
User selects model → onModelChange(model) called
  → setModel(agentId, model) in hook
  → POST {sdkBase}/sessions/{sdkSid}/config  { model }
  → on success: setCurrentModel(model) — local state override
  → on error: brief inline error shown in the pill area
```

The agent-sdk endpoint (`POST /sessions/{id}/config`) already exists and handles `{ model }` — no server changes needed.

Note: calling the agent-sdk config endpoint does NOT update the Hive database. `activeAgent.model` from the server will still show the creation-time model. The pill therefore tracks model in local React state (`currentModel`), initialized from `activeAgent.model` and updated optimistically on success.

## Components

### `setModel` in `use-workspace-agent.ts`

```ts
setModel(agentId: string, model: string): Promise<void>
```

Reads `connectionsRef.current[agentId]` for `sdkBase`/`sdkSid`, calls:
```
POST {sdkBase}/sessions/{sdkSid}/config
Content-Type: application/json
{ "model": model }
```

Returns without throwing on network error (caller handles error state).

### Model pill + dropdown in `AgentTabs`

New props added to `AgentTabs`:
```ts
activeModel: string | null
onModelChange: (model: string) => Promise<void>
```

UI:
- **Pill**: small monospace badge on the right of the tabs strip, always visible when `activeModel` is set. Shows short name (`haiku`, `sonnet-4-6`, `opus-4-6`). Chevron toggles up/down.
- **Dropdown**: absolute-positioned below the pill, three items:
  - `Haiku` — `claude-haiku-4-5-20251001` — "Fast" badge
  - `Sonnet` — `claude-sonnet-4-6` — "Balanced" badge  
  - `Opus` — `claude-opus-4-6` — "Powerful" badge
  - Checkmark on current selection
- Closes on outside click (via `useEffect` + `document.addEventListener`)
- During the async call: pill shows a brief spinner; dropdown stays closed

### Model constants

The ACP has no `models/list` endpoint — `session/set_config_option` sets a model but there's no query to fetch available ones. The list is hardcoded in the UI (one-line update when new models ship):

```ts
const MODELS = [
  { id: "claude-haiku-4-5-20251001", label: "Haiku",  tier: "Fast",      short: "haiku" },
  { id: "claude-sonnet-4-6",         label: "Sonnet", tier: "Balanced",   short: "sonnet-4-6" },
  { id: "claude-opus-4-6",           label: "Opus",   tier: "Powerful",   short: "opus-4-6" },
] as const;
```

## Error Handling

- If `connectionsRef` has no entry for `agentId` (not yet connected), `setModel` is a no-op.
- If the `POST /config` call fails (non-2xx), `setModel` throws; `handleModelChange` in `page.tsx` catches and sets a brief `modelError` state rendered below the pill ("Failed to switch model").
- No optimistic update — pill label only changes after `refetchWorkspace()` succeeds.

## What Does Not Change

- Agent creation still defaults to `claude-sonnet-4-6` at `page.tsx:668`. The selector changes the running session, not the creation default.
- No changes to the agent-sdk server, Hive backend, or database schema — `WorkspaceAgent.model` in the DB is updated implicitly when the agent re-registers after a model change, not by the frontend.
- No changes to any page other than the workspace page.

## Scope

- Single file changes: `use-workspace-agent.ts`, `page.tsx`
- No new files, no new dependencies
