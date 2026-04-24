from __future__ import annotations
import os
from agent_sdk.server_client import ServerClient

_BASE = os.environ.get("AGENT_SDK_BASE_URL", "")
_TOKEN = os.environ.get("AGENT_SDK_TOKEN", "") or None
_TIMEOUT = float(os.environ.get("AGENT_SDK_TIMEOUT_SEC", "30"))

# Module-level singleton. If AGENT_SDK_BASE_URL is unset, construction still
# succeeds (base_url becomes empty) — first real request will fail loudly.
# Hive's backend always sets this env var in production.
sdk = ServerClient(_BASE, token=_TOKEN, timeout=_TIMEOUT)


async def close_sdk() -> None:
    await sdk.close()
