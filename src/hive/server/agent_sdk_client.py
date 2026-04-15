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

    async def create_quick_session(self, **config: Any) -> dict[str, Any]:
        return await self._json("POST", "/sessions/quick", json=config)

    async def get_status(self, sid: str) -> dict[str, Any]:
        return await self._json("GET", f"/sessions/{sid}/status")

    async def get_log(self, sid: str, limit: int = 500) -> list[dict[str, Any]]:
        data = await self._json("GET", f"/sessions/{sid}/log", params={"limit": limit})
        events = data.get("events") if isinstance(data, dict) else data
        return events or []

    async def send_message(
        self, sid: str, text: str, interrupt: bool = False
    ) -> dict[str, Any]:
        return await self._json(
            "POST",
            f"/sessions/{sid}/message",
            json={"message": text, "interrupt": interrupt},
        )

    async def cancel(self, sid: str) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/cancel")

    async def resume(self, sid: str) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/resume")

    async def set_config(self, sid: str, **kwargs: Any) -> dict[str, Any]:
        return await self._json("POST", f"/sessions/{sid}/config", json=kwargs)

    async def destroy_sandbox(self, sandbox_id: str) -> None:
        try:
            await self._client.delete(f"/sandboxes/{sandbox_id}")
        except Exception as e:
            log.warning("destroy_sandbox %s failed: %s", sandbox_id, e)

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
