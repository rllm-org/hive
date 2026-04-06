"""User agent connection endpoints for sandbox providers.

Supports browser_oauth flow:
  1. begin → generates state, returns browser_url
  2. user opens browser_url, submits API key on the auth page
  3. callback stores encrypted credential, marks connected
  4. original caller polls list endpoint and sees connected
"""

from __future__ import annotations

import json
import os
import secrets
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from .crypto import decrypt_value, encrypt_value
from .db import get_db, now
from .sandbox_contract import normalize_provider

router = APIRouter()

HIVE_SERVER_URL = os.environ.get("HIVE_SERVER_URL", "").rstrip("/")


async def _require_user(authorization: str = Header(...)) -> dict:
    from . import main as main_mod

    return await main_mod.require_user(authorization)


# --- Connection CRUD ---


@router.get("/users/me/agent-connections")
async def list_agent_connections(user: dict = Depends(_require_user)):
    user_id = int(user["sub"])
    async with get_db() as conn:
        rows = await (
            await conn.execute(
                "SELECT id, provider, auth_mode, status, metadata_json, created_at, updated_at"
                " FROM user_agent_connections WHERE user_id = %s ORDER BY provider",
                (user_id,),
            )
        ).fetchall()
    connections = []
    for r in rows:
        c = dict(r)
        if c.get("metadata_json"):
            try:
                c["metadata"] = json.loads(c.pop("metadata_json"))
            except (json.JSONDecodeError, TypeError):
                c["metadata"] = {}
                del c["metadata_json"]
        else:
            c.pop("metadata_json", None)
            c["metadata"] = {}
        connections.append(c)
    return {"connections": connections}


@router.post("/users/me/agent-connections/{provider}/begin")
async def agent_connection_begin(provider: str, body: dict[str, Any], user: dict = Depends(_require_user)):
    user_id = int(user["sub"])
    try:
        p = normalize_provider(provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    auth_mode = body.get("auth_mode", "api_key")
    if auth_mode not in ("browser_oauth", "device_code", "api_key", "auth_file"):
        raise HTTPException(400, "invalid auth_mode")
    ts = now()

    if auth_mode == "browser_oauth":
        # Generate state token, store in oauth_states, return browser URL.
        state = secrets.token_urlsafe(32)
        expires = ts + timedelta(minutes=15)
        mode_tag = f"agent_connect:{user_id}:{p}"
        async with get_db() as conn:
            await conn.execute(
                "INSERT INTO oauth_states (token, mode, expires_at) VALUES (%s, %s, %s)"
                " ON CONFLICT (token) DO UPDATE SET mode = EXCLUDED.mode, expires_at = EXCLUDED.expires_at",
                (state, mode_tag, expires),
            )
            await conn.execute(
                """INSERT INTO user_agent_connections (user_id, provider, auth_mode, status, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (user_id, provider) DO UPDATE SET
                     auth_mode = EXCLUDED.auth_mode,
                     status = EXCLUDED.status,
                     updated_at = EXCLUDED.updated_at""",
                (user_id, p, auth_mode, "pending", ts, ts),
            )
        base = HIVE_SERVER_URL or body.get("server_url", "")
        browser_url = f"{base}/api/auth/agent-providers/{p}/authorize?state={state}"
        return {
            "status": "pending",
            "provider": p,
            "auth_mode": auth_mode,
            "browser_url": browser_url,
            "state": state,
            "expires_in": 900,
        }

    # Non-browser modes: just create pending row.
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO user_agent_connections (user_id, provider, auth_mode, status, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (user_id, provider) DO UPDATE SET
                 auth_mode = EXCLUDED.auth_mode,
                 status = EXCLUDED.status,
                 updated_at = EXCLUDED.updated_at""",
            (user_id, p, auth_mode, "pending", ts, ts),
        )
    return {"status": "pending", "provider": p, "auth_mode": auth_mode}


@router.post("/users/me/agent-connections/{provider}/complete")
async def agent_connection_complete(provider: str, body: dict[str, Any], user: dict = Depends(_require_user)):
    user_id = int(user["sub"])
    try:
        p = normalize_provider(provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    secret = body.get("credential") or body.get("token")
    if not secret or not isinstance(secret, str):
        raise HTTPException(400, "credential or token required")
    enc = encrypt_value(secret)
    auth_mode = body.get("auth_mode", "api_key")
    if auth_mode not in ("browser_oauth", "device_code", "api_key", "auth_file"):
        auth_mode = "api_key"
    ts = now()
    metadata = json.dumps({"credential_type": "api_key", "connected_at": ts.isoformat(), "auth_flow": auth_mode})
    async with get_db() as conn:
        await conn.execute(
            """INSERT INTO user_agent_connections
               (user_id, provider, auth_mode, status, encrypted_credential_ref, metadata_json, created_at, updated_at)
               VALUES (%s, %s, %s, 'connected', %s, %s, %s, %s)
               ON CONFLICT (user_id, provider) DO UPDATE SET
                 auth_mode = EXCLUDED.auth_mode,
                 encrypted_credential_ref = EXCLUDED.encrypted_credential_ref,
                 metadata_json = EXCLUDED.metadata_json,
                 status = 'connected',
                 updated_at = EXCLUDED.updated_at""",
            (user_id, p, auth_mode, enc, metadata, ts, ts),
        )
    return {"status": "connected", "provider": p}


@router.delete("/users/me/agent-connections/{provider}")
async def agent_connection_delete(provider: str, user: dict = Depends(_require_user)):
    user_id = int(user["sub"])
    try:
        p = normalize_provider(provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    async with get_db() as conn:
        await conn.execute(
            "UPDATE user_agent_connections SET encrypted_credential_ref = NULL,"
            " status = 'disconnected', updated_at = %s WHERE user_id = %s AND provider = %s",
            (now(), user_id, p),
        )
        await conn.execute(
            "DELETE FROM user_agent_connections WHERE user_id = %s AND provider = %s",
            (user_id, p),
        )
    return {"status": "ok"}


@router.get("/users/me/agent-connections/{provider}/status")
async def agent_connection_status(provider: str, user: dict = Depends(_require_user)):
    """Poll endpoint for checking if browser_oauth completed."""
    user_id = int(user["sub"])
    try:
        p = normalize_provider(provider)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT status, auth_mode, metadata_json FROM user_agent_connections"
                " WHERE user_id = %s AND provider = %s",
                (user_id, p),
            )
        ).fetchone()
    if not row:
        return {"status": "not_found", "provider": p}
    return {"status": row["status"], "provider": p, "auth_mode": row["auth_mode"]}


# --- Browser OAuth authorize page + callback ---

_AUTH_PAGE_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect {provider} — Hive</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; color: #222; }}
  h2 {{ font-size: 1.3em; }}
  input[type=password] {{ width: 100%; padding: 10px; font-size: 14px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }}
  button {{ margin-top: 12px; padding: 10px 24px; font-size: 14px; background: #222; color: #fff; border: none; border-radius: 4px; cursor: pointer; }}
  button:hover {{ background: #444; }}
  .hint {{ font-size: 12px; color: #666; margin-top: 8px; }}
  .err {{ color: #c00; }}
</style></head><body>
<h2>Connect {provider_label}</h2>
<p>Paste your API key below. Get one from
<a href="https://console.anthropic.com/settings/keys" target="_blank">console.anthropic.com</a>.</p>
<form method="POST" action="/api/auth/agent-providers/{provider}/callback">
  <input type="hidden" name="state" value="{state}">
  <input type="password" name="credential" placeholder="sk-ant-..." required autofocus>
  <button type="submit">Connect</button>
</form>
<p class="hint">Your key is encrypted at rest and only used inside sandboxes.</p>
</body></html>"""

_SUCCESS_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connected — Hive</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; color: #222; }
  .ok { color: #080; font-size: 1.3em; }
</style></head><body>
<p class="ok">Connected.</p>
<p>You can close this window and return to Hive.</p>
</body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error — Hive</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 480px; margin: 60px auto; padding: 0 20px; color: #222; }}
  .err {{ color: #c00; }}
</style></head><body>
<p class="err">{message}</p>
</body></html>"""

_PROVIDER_LABELS = {"claude_code": "Claude Code", "codex": "Codex", "opencode": "OpenCode"}


@router.get("/auth/agent-providers/{provider}/authorize")
async def authorize_page(provider: str, state: str = Query(...)):
    """Serve the browser auth page where the user pastes their API key."""
    try:
        p = normalize_provider(provider)
    except ValueError:
        return HTMLResponse(_ERROR_HTML.format(message="Unknown provider."), status_code=400)
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT token, mode, expires_at FROM oauth_states WHERE token = %s",
                (state,),
            )
        ).fetchone()
    if not row:
        return HTMLResponse(_ERROR_HTML.format(message="Invalid or expired auth link."), status_code=400)
    if row["expires_at"] < now():
        return HTMLResponse(_ERROR_HTML.format(message="This auth link has expired. Please start again."), status_code=400)
    if not row["mode"].startswith(f"agent_connect:"):
        return HTMLResponse(_ERROR_HTML.format(message="Invalid auth state."), status_code=400)

    label = _PROVIDER_LABELS.get(p, p)
    html = _AUTH_PAGE_HTML.format(provider=p, provider_label=label, state=state)
    return HTMLResponse(html)


@router.post("/auth/agent-providers/{provider}/callback")
async def authorize_callback(provider: str, state: str = Form(""), credential: str = Form("")):
    """Handle the form submission from the browser auth page."""
    try:
        p = normalize_provider(provider)
    except ValueError:
        return HTMLResponse(_ERROR_HTML.format(message="Unknown provider."), status_code=400)

    if not state or not credential:
        return HTMLResponse(_ERROR_HTML.format(message="Missing state or credential."), status_code=400)

    # Validate state
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "DELETE FROM oauth_states WHERE token = %s RETURNING mode, expires_at",
                (state,),
            )
        ).fetchone()
    if not row:
        return HTMLResponse(_ERROR_HTML.format(message="Invalid or already-used auth link."), status_code=400)
    if row["expires_at"] < now():
        return HTMLResponse(_ERROR_HTML.format(message="This auth link has expired."), status_code=400)

    # Parse mode to get user_id and provider
    parts = row["mode"].split(":")
    if len(parts) != 3 or parts[0] != "agent_connect":
        return HTMLResponse(_ERROR_HTML.format(message="Invalid auth state."), status_code=400)
    user_id = int(parts[1])
    state_provider = parts[2]
    if state_provider != p:
        return HTMLResponse(_ERROR_HTML.format(message="Provider mismatch."), status_code=400)

    # Store encrypted credential
    enc = encrypt_value(credential)
    ts = now()
    metadata = json.dumps({"credential_type": "api_key", "connected_at": ts.isoformat(), "auth_flow": "browser_oauth"})
    async with get_db() as conn:
        await conn.execute(
            """UPDATE user_agent_connections
               SET auth_mode = 'browser_oauth', status = 'connected',
                   encrypted_credential_ref = %s, metadata_json = %s, updated_at = %s
               WHERE user_id = %s AND provider = %s""",
            (enc, metadata, ts, user_id, p),
        )

    return HTMLResponse(_SUCCESS_HTML)


# --- Credential loading (used by sandbox routes) ---


async def load_provider_credential(user_id: int, provider: str) -> str | None:
    """Load and decrypt the stored credential for a provider connection.
    Returns the plaintext credential or None if not connected."""
    async with get_db() as conn:
        row = await (
            await conn.execute(
                "SELECT status, encrypted_credential_ref FROM user_agent_connections"
                " WHERE user_id = %s AND provider = %s",
                (user_id, provider),
            )
        ).fetchone()
    if not row or row["status"] != "connected" or not row["encrypted_credential_ref"]:
        return None
    return decrypt_value(row["encrypted_credential_ref"])
