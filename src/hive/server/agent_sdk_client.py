"""Thin async wrapper around the agent-sdk REST API.

The agent-sdk service (rllm-org/agent-sdk, deployed separately) owns ACP,
sandbox lifecycle, and prompt queue/scheduler. Hive just proxies to it.

Reads AGENT_SDK_BASE_URL + AGENT_SDK_TOKEN from env. Endpoints documented at
https://github.com/rllm-org/agent-sdk/blob/main/docs/api.md.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import HTTPException

log = logging.getLogger("hive.agent_sdk")

AGENT_SDK_BASE_URL = os.environ.get("AGENT_SDK_BASE_URL", "")
AGENT_SDK_TOKEN = os.environ.get("AGENT_SDK_TOKEN", "")
AGENT_SDK_TIMEOUT_SEC = float(os.environ.get("AGENT_SDK_TIMEOUT_SEC", "30"))


class AgentSdkClient:
    def __init__(self, base_url: str, token: str, timeout: float):
        self._base = base_url.rstrip("/")
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=headers,
            timeout=httpx.Timeout(timeout, read=None),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _json(self, method: str, path: str, **kw) -> dict[str, Any]:
        resp = await self._client.request(method, path, **kw)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"agent-sdk {method} {path} -> {resp.status_code}: {resp.text[:500]}",
            )
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {}

    async def create_quick_session(self, oauth_token: str | None = None, **config: Any) -> dict[str, Any]:
        body = dict(config)
        if oauth_token:
            secrets = body.setdefault("secrets", {})
            secrets["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        return await self._json("POST", "/sessions/quick", json=body)

    async def create_session(self, sandbox_id: str, oauth_token: str | None = None, **config: Any) -> dict[str, Any]:
        body: dict[str, Any] = {"sandbox_id": sandbox_id, **config}
        if oauth_token:
            body["oauth_token"] = oauth_token
        return await self._json("POST", "/sessions", json=body)

    async def create_session_lazy(self, oauth_token: str | None = None, **config: Any) -> dict[str, Any]:
        """Create a session without provisioning a sandbox. Sandbox is created
        lazily on the first /message or /resume."""
        body = dict(config)
        if oauth_token:
            secrets = body.setdefault("secrets", {})
            secrets["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
        return await self._json("POST", "/sessions", json=body)

    async def get_status(self, sid: str) -> dict[str, Any]:
        return await self._json("GET", f"/sessions/{sid}/status")

    async def get_log(self, sid: str, limit: int = 500) -> list[dict[str, Any]]:
        data = await self._json("GET", f"/sessions/{sid}/log", params={"limit": limit})
        events = data.get("events") if isinstance(data, dict) else data
        return events or []

    async def send_message(self, sid: str, text: str, interrupt: bool = False) -> dict[str, Any]:
        return await self._json(
            "POST", f"/sessions/{sid}/message",
            json={"message": text, "interrupt": interrupt},
        )

    async def cancel(self, sid: str) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/cancel")

    async def resume(self, sid: str) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/resume")

    async def set_config(self, sid: str, **kwargs: Any) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/config", json=kwargs)

    async def sandbox_exec(self, sid: str, command: str, timeout: int = 120) -> dict[str, Any]:
        return await self._json(
            "POST", f"/sessions/{sid}/sandbox/exec",
            json={"command": command, "timeout": timeout},
        )

    async def provision_sandbox(self, oauth_token: str | None = None, **config: Any) -> dict[str, Any]:
        """Provision a sandbox with deps installed, no supervisor started.

        If ``oauth_token`` is supplied, agent-sdk encrypts and persists it on
        the sandbox row — every subsequent supervisor spawn in that sandbox
        (initial, auto-recovery after idle-stop, resume) picks it up without
        further plumbing from hive.
        """
        body = dict(config)
        if oauth_token:
            body["oauth_token"] = oauth_token
        return await self._json("POST", "/sandboxes/provision", json=body)

    async def rotate_sandbox_creds(self, sandbox_id: str, oauth_token: str | None) -> dict[str, Any]:
        """Update (or wipe) the user creds stored on a sandbox row. Called
        when a user reconnects or disconnects their Claude account so their
        live sandboxes pick up the new creds on next supervisor spawn."""
        body: dict[str, Any] = {}
        if oauth_token:
            body["oauth_token"] = oauth_token
        return await self._json("PUT", f"/sandboxes/{sandbox_id}/creds", json=body)

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        try:
            await self._client.delete(f"/sandboxes/{sandbox_id}")
        except Exception as e:
            log.warning("destroy_sandbox %s failed: %s", sandbox_id, e)

    async def list_sessions(self) -> list[dict[str, Any]]:
        data = await self._json("GET", "/sessions")
        return data if isinstance(data, list) else data.get("sessions", [])

    async def volume_file_tree(self, volume_id: str, path: str = "") -> dict[str, Any]:
        params = {"path": path} if path else {}
        return await self._json("GET", f"/volumes/{volume_id}/files/tree", params=params)

    async def volume_file_read(self, volume_id: str, path: str) -> dict[str, Any]:
        return await self._json("GET", f"/volumes/{volume_id}/files/read", params={"path": path})

    async def volume_file_write(self, volume_id: str, path: str, content: str = "") -> dict[str, Any]:
        """Write (create or overwrite) a file on the volume."""
        return await self._json("POST", f"/volumes/{volume_id}/files/edit", json={"path": path, "content": content})

    async def volume_file_edit(self, volume_id: str, path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {"path": path, "old_string": old_string, "new_string": new_string}
        if replace_all:
            body["replace_all"] = True
        return await self._json("POST", f"/volumes/{volume_id}/files/edit", json=body)

    async def delete_session(self, sid: str) -> None:
        try:
            await self._client.delete(f"/sessions/{sid}")
        except Exception as e:
            log.warning("delete_session %s failed: %s", sid, e)

    async def stream_events(self, sid: str) -> AsyncIterator[bytes]:
        """Yield raw SSE bytes from GET /sessions/{sid}/events.

        Caller is responsible for framing. On client disconnect, the async
        generator is closed and the upstream stream is cancelled.
        """
        async with self._client.stream("GET", f"/sessions/{sid}/events") as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise HTTPException(
                    status_code=502,
                    detail=f"agent-sdk events -> {resp.status_code}: {body[:500].decode('utf-8', 'replace')}",
                )
            async for chunk in resp.aiter_bytes():
                yield chunk


_client: AgentSdkClient | None = None


def get_client() -> AgentSdkClient:
    if not AGENT_SDK_BASE_URL:
        raise HTTPException(503, "AGENT_SDK_BASE_URL not configured")
    global _client
    if _client is None:
        _client = AgentSdkClient(AGENT_SDK_BASE_URL, AGENT_SDK_TOKEN, AGENT_SDK_TIMEOUT_SEC)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
