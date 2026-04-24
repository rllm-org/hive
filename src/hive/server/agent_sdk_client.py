"""Thin async wrapper around the agent-sdk REST API.

Only used for operations the frontend can't do directly:
- Volume file ops (workspace Files tab)
- Sending messages to agents (mention dispatch)
- Session/sandbox cleanup (agent deletion)

Session creation uses the agent_sdk Python SDK. Frontend talks to
agent-sdk directly for SSE, messages, cancel, config, file browsing.
"""

from __future__ import annotations

import logging
import os
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

    # --- Mention dispatch ---

    async def send_message(self, sid: str, text: str, interrupt: bool = False) -> dict[str, Any]:
        return await self._json(
            "POST", f"/sessions/{sid}/message",
            json={"message": text, "interrupt": interrupt},
        )

    # --- Volume file ops (workspace Files tab proxy) ---

    async def volume_file_tree(self, volume_id: str, path: str = "") -> dict[str, Any]:
        params = {"path": path} if path else {}
        return await self._json("GET", f"/volumes/{volume_id}/files/tree", params=params)

    async def volume_file_read(self, volume_id: str, path: str) -> dict[str, Any]:
        return await self._json("GET", f"/volumes/{volume_id}/files/read", params={"path": path})

    async def volume_file_write(self, volume_id: str, path: str, content: str = "") -> dict[str, Any]:
        return await self._json("POST", f"/volumes/{volume_id}/files/edit", json={"path": path, "content": content})

    # --- Cleanup ---

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        try:
            await self._client.delete(f"/sandboxes/{sandbox_id}")
        except Exception as e:
            log.warning("destroy_sandbox %s failed: %s", sandbox_id, e)

    async def delete_session(self, sid: str) -> None:
        try:
            await self._client.delete(f"/sessions/{sid}")
        except Exception as e:
            log.warning("delete_session %s failed: %s", sid, e)


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
