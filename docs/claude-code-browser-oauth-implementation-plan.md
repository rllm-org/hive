# Claude Code Browser OAuth Implementation Plan

## Goal

Implement real browser-based login for `claude_code` so a Hive user can:

1. Connect Claude Code through a browser OAuth flow.
2. Store the resulting credential securely in Hive.
3. Launch Claude Code inside a Daytona sandbox using that credential.
4. Persist Claude Code output and lifecycle events in Postgres.

This plan is written to be handed directly to an implementation agent.

## Current State

What already exists:

- `user_agent_connections` table stores provider connections per user.
- `browser_oauth` is accepted as an auth mode for provider connections.
- `POST /users/me/agent-connections/{provider}/begin` creates a pending row.
- `POST /users/me/agent-connections/{provider}/complete` stores an encrypted credential.
- Private-task sandboxes can be created in Daytona.
- Sandbox sessions can be created and basic session events can be stored.

What is missing:

- No real Claude Code browser OAuth URL is generated today.
- No callback flow completes Claude auth automatically.
- No code injects the stored Claude credential into the Daytona sandbox.
- No code launches Claude Code inside Daytona.
- No code tails Claude Code output and converts it into `agent_session_events`.

## Success Criteria

By the end of this work:

- A user can click or invoke "connect Claude Code" and get a real browser login flow.
- After successful auth, Hive stores a valid encrypted Claude credential in `user_agent_connections`.
- Starting a `claude_code` sandbox session uses that credential inside the Daytona sandbox.
- Claude Code runs inside the sandbox in the requested working directory.
- User prompts can be forwarded to Claude Code.
- Claude Code output is stored in Postgres as structured events.
- Sandbox/system logs are stored separately from conversational events.
- Secrets are never written to logs or transcripts.

## Non-Goals

- Supporting every provider end-to-end in the first pass.
- Building a generic multi-provider adapter framework before Claude Code works.
- Perfect long-term auth refresh/recovery on day one.
- Rich UI polish beyond what is needed to prove the flow works.

## Constraints From Current Codebase

- `user_agent_connections` already exists and should remain the source of truth for provider credentials.
- `task_sandboxes` stores sandbox lifecycle metadata.
- `agent_sessions` stores session metadata.
- `agent_session_events` is the structured event log for session activity.
- `sandbox_log_chunks` stores sandbox/system log chunks.
- Current `sandbox_routes.py` provisions Daytona and appends only basic Hive-generated events/logs.

## High-Level Architecture

Target flow:

1. User begins Claude Code browser OAuth.
2. Hive creates a provider-specific pending auth state and returns a real `browser_url`.
3. User completes auth in browser.
4. Hive callback exchanges the auth result for a Claude credential or session artifact.
5. Hive encrypts and stores that artifact in `user_agent_connections`.
6. User starts a private-task sandbox session with provider `claude_code`.
7. Hive runner looks up the stored Claude credential, decrypts it, and materializes it into the Daytona sandbox.
8. Hive runner launches Claude Code inside the sandbox.
9. Hive runner forwards prompts and captures output.
10. Hive writes structured events to `agent_session_events` and runner/system logs to `sandbox_log_chunks`.

## Implementation Phases

### Phase 1: Confirm Claude Code auth contract

Objective:

- Determine exactly what Claude Code needs after browser auth in order to run non-interactively inside a sandbox.

Tasks:

- Verify whether Claude Code supports:
  - API key auth
  - imported auth file
  - browser OAuth session artifact
  - device code fallback
- Identify the credential shape that should be stored in Hive:
  - opaque token
  - refreshable token set
  - auth file JSON
  - cookie/session blob
- Identify how Claude Code expects that credential at runtime:
  - environment variable
  - config file in a known location
  - one-time login import command

Deliverable:

- A short internal note in the repo documenting the chosen credential format and runtime injection method.

Acceptance criteria:

- There is one explicit chosen credential format for `claude_code`.
- There is one explicit chosen runtime injection path for the sandbox.

### Phase 2: Implement real browser OAuth start + callback

Objective:

- Replace the current placeholder `browser_oauth` scaffolding with a real auth round-trip.

Primary files:

- `src/hive/server/sandbox_agent_connections.py`
- optionally new `src/hive/server/provider_auth.py`
- optionally shared helpers in `src/hive/server/main.py`

Tasks:

- Extend `POST /users/me/agent-connections/{provider}/begin` for `provider=claude_code` and `auth_mode=browser_oauth`:
  - generate provider-specific OAuth state
  - store pending metadata in `user_agent_connections.metadata_json` or a dedicated temporary auth store
  - return a real `browser_url`
- Add a callback endpoint such as:
  - `GET /auth/agent-providers/claude_code/callback`
- In the callback:
  - validate state
  - exchange the auth code for the Claude credential/session artifact
  - encrypt and store it in `user_agent_connections.encrypted_credential_ref`
  - set `status = 'connected'`
  - update `metadata_json` with safe non-secret metadata
- Preserve existing `api_key` behavior.

Suggested data to store in `metadata_json`:

- `credential_type`
- `connected_at`
- `account_label` if available
- `last_auth_flow`
- `oauth_state_created_at`

Acceptance criteria:

- `begin` returns a non-null `browser_url` for Claude Code browser OAuth.
- Callback validates and completes the auth flow.
- The resulting connection row is `connected`.
- The secret is encrypted before storage.

### Phase 3: Improve connection state model

Objective:

- Make provider connection rows descriptive enough for runtime checks and UX.

Primary files:

- `src/hive/server/db.py`
- `src/hive/server/sandbox_agent_connections.py`

Tasks:

- Keep existing schema if possible and use `metadata_json` first.
- If needed, add additive columns:
  - `credential_type TEXT`
  - `error_message TEXT`
  - `last_verified_at TIMESTAMPTZ`
- Standardize connection statuses:
  - `pending`
  - `connected`
  - `expired`
  - `error`
  - `disconnected`

Acceptance criteria:

- Connection rows make it obvious whether Claude Code is usable for sandbox launch.
- Error cases are visible without exposing secrets.

### Phase 4: Build a Claude Code sandbox runner

Objective:

- Add the missing execution layer that actually starts Claude Code inside Daytona.

Primary files:

- new `src/hive/server/sandbox_runner.py`
- `src/hive/server/sandbox_routes.py`
- `src/hive/server/daytona_runtime.py`
- `src/hive/server/sandbox_helpers.py`

Tasks:

- Introduce a runner abstraction for sandbox sessions.
- For `claude_code` sessions:
  - load the user's connection row
  - decrypt the stored credential
  - materialize the credential inside Daytona
  - launch Claude Code in the requested `cwd`
- Decide whether to implement the runner:
  - inline in the server process first
  - or behind `adapter_base_url`

Recommended first implementation:

- Keep the runner in-process or tightly coupled to the server until the end-to-end flow works.
- Only externalize to an adapter service later if needed.

Acceptance criteria:

- A `claude_code` session starts an actual Claude Code process in Daytona.
- Launch fails clearly if no valid Claude connection exists.

### Phase 5: Materialize Claude auth safely inside the sandbox

Objective:

- Make the stored Claude credential usable by the in-sandbox Claude Code process.

Primary files:

- `src/hive/server/sandbox_runner.py`
- `src/hive/server/daytona_runtime.py`

Tasks:

- Based on Phase 1 findings, implement one runtime injection path:
  - env var injection
  - auth file materialization
  - login bootstrap command
- Ensure:
  - secrets are never printed
  - file permissions are restrictive if writing auth files
  - temporary auth files are deleted on sandbox shutdown when possible
- Redact credentials if any subprocess output accidentally echoes them.

Acceptance criteria:

- Claude Code can start authenticated inside the sandbox.
- No credential value appears in logs, session events, or error messages.

### Phase 6: Persist Claude Code output and events

Objective:

- Convert Claude Code process activity into durable Postgres records.

Primary files:

- `src/hive/server/sandbox_runner.py`
- `src/hive/server/sandbox_helpers.py`
- `src/hive/server/sandbox_contract.py`

Tasks:

- Capture Claude Code stdout/stderr from the runner.
- Append structured session events such as:
  - `message.assistant`
  - `stdout.chunk`
  - `stderr.chunk`
  - `tool.call.started`
  - `tool.call.finished`
  - `permission.requested`
  - `permission.resolved`
  - `session.completed`
  - `session.failed`
- Append lower-level runner/system logs to `sandbox_log_chunks`.
- Keep the split clear:
  - `agent_session_events` for structured conversational/runtime events
  - `sandbox_log_chunks` for sandbox/system logs

Acceptance criteria:

- After sending a prompt, new rows appear in `agent_session_events`.
- Runner/system logs appear in `sandbox_log_chunks`.
- Events are ordered by `seq` and readable via existing API endpoints.

### Phase 7: Wire prompt delivery into the running Claude session

Objective:

- Make `POST /tasks/{task_id}/sandbox/sessions/{session_id}/messages` actually reach the Claude process.

Primary files:

- `src/hive/server/sandbox_routes.py`
- `src/hive/server/sandbox_runner.py`

Tasks:

- Keep the existing `message.user` event append.
- Add runtime forwarding so the message is sent to the active Claude Code process.
- Update session state as needed.

Acceptance criteria:

- Sending a session message causes Claude Code to receive it.
- A corresponding assistant response or process output is eventually persisted.

### Phase 8: Update CLI and UI for real browser auth

Objective:

- Make the feature usable from both CLI and web UI.

Primary files:

- `src/hive/cli/cmd_sandbox.py`
- `ui/src/components/sandbox-panel.tsx`
- optionally new UI components for provider connections

Tasks:

- CLI:
  - for `browser_oauth`, print the real `browser_url`
  - optionally open the browser automatically
  - add a wait/poll helper if useful
- UI:
  - show `Connect Claude Code`
  - handle pending state
  - poll for completion after callback
  - show connected/disconnected/error states
  - block session start if no Claude connection exists

Acceptance criteria:

- A user can connect Claude Code without manual DB manipulation or secret copy/paste.
- UX clearly shows whether the provider is ready.

### Phase 9: Add security hardening

Objective:

- Ensure the flow is safe for multi-user hosted deployment.

Primary files:

- `src/hive/server/sandbox_agent_connections.py`
- `src/hive/server/sandbox_runner.py`
- `src/hive/server/main.py`

Tasks:

- Restrict provider connections to the owning user.
- Ensure only the owning user can consume their Claude connection for sandbox launch.
- Redact secret patterns in logs and events.
- Make disconnect delete the stored credential immediately.
- Handle expired or invalid credentials gracefully.

Acceptance criteria:

- Credentials cannot be read or used across users.
- Secret leakage tests pass.

## Data Model Usage

Use the existing tables like this:

- `user_agent_connections`
  - source of truth for Claude browser auth state and encrypted credential
- `task_sandboxes`
  - sandbox lifecycle metadata
- `agent_sessions`
  - session metadata, provider choice, approval mode, launch info
- `agent_session_events`
  - structured user/assistant/tool/permission/state events
- `sandbox_log_chunks`
  - sandbox lifecycle logs and runner/system logs

## Suggested API Shape

Keep existing endpoints and extend them:

- `POST /users/me/agent-connections/claude_code/begin`
  - with `auth_mode = browser_oauth`
  - returns `{ status, provider, auth_mode, browser_url, ... }`
- `GET /auth/agent-providers/claude_code/callback`
  - completes OAuth and persists credential
- `GET /users/me/agent-connections`
  - returns enough metadata for UI/CLI to show status
- `POST /tasks/{task_id}/sandbox/sessions`
  - validates that Claude connection is available before launch when provider is `claude_code`

## Suggested Internal Interfaces

Introduce small internal interfaces instead of over-generalizing:

- `begin_provider_oauth(provider, user_id) -> browser_url`
- `complete_provider_oauth(provider, state, code) -> credential_payload`
- `load_provider_connection(user_id, provider) -> connection`
- `materialize_provider_auth_in_sandbox(connection, sandbox) -> runtime_auth_info`
- `launch_provider_session(provider, sandbox, runtime_auth_info, cwd, approval_mode, options) -> process_handle`
- `pump_provider_output(process_handle, session_id, sandbox_id) -> background task`

## Testing Plan

### Server tests

Primary test files:

- `tests/server/test_sandbox_agent_connections.py`
- new `tests/server/test_sandbox_runner.py`
- update any existing sandbox route tests as needed

Add tests for:

- begin returns real browser URL for Claude Code
- callback validates state and stores encrypted credential
- connection status transitions from `pending` to `connected`
- session creation fails if Claude connection is missing
- session creation succeeds if Claude connection exists
- runner materializes auth without logging secrets
- user messages produce `message.user` events
- simulated Claude output produces `message.assistant` and chunk events
- sandbox/system logs are written to `sandbox_log_chunks`
- unauthorized users cannot use another user's provider connection

### Integration tests

Add one focused end-to-end test path:

1. connect Claude Code
2. create private-task sandbox
3. create `claude_code` session
4. send a prompt
5. verify at least one assistant or stdout event appears

Mock the external provider exchange if needed. Do not require real live Claude auth in CI.

## Rollout Strategy

Recommended rollout:

1. Ship real browser OAuth start + callback first.
2. Ship sandbox runner with minimal authenticated Claude launch.
3. Ship message forwarding and basic output capture.
4. Ship richer event mapping and UI polish.

## Minimal First Vertical Slice

If you want the fastest path to working behavior, implement only this first:

1. Real Claude Code `browser_oauth` flow with callback.
2. Encrypted credential stored in `user_agent_connections`.
3. `claude_code` session startup validates and loads the stored connection.
4. Runner launches Claude Code in Daytona using that credential.
5. Persist:
   - `session.started`
   - `message.user`
   - `stdout.chunk`
   - `stderr.chunk`
   - `message.assistant` if feasible

Everything else can come after that.

## Explicit Deliverables

The implementing agent should produce:

- working backend auth flow for Claude Code browser OAuth
- secure credential persistence
- Claude Code launch path inside Daytona
- event/log persistence into Postgres
- minimal CLI and UI support
- focused automated tests
- updated documentation describing the completed flow

## Notes For The Implementing Agent

- Do not invent a generic provider platform before Claude Code works end-to-end.
- Prefer additive schema changes only.
- Reuse the existing tables and endpoints where practical.
- Keep secrets out of logs, events, exceptions, and test snapshots.
- If Claude Code's actual auth artifact differs from expectations, update this plan's credential contract first, then proceed with implementation.
