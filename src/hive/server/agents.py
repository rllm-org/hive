from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import HTTPException

from .sdk import sdk

log = logging.getLogger("hive.agents")


async def create_agent_session(
    *,
    agent_row: dict,
    workspace_row: dict,
    body: dict[str, Any],
    user_oauth_token: str | None,
    system_prompt: str,
    provider: str,
    global_volume_id: str,
    hive_server_url: str,
) -> str:
    workspace_id = workspace_row["id"]
    model_name = (body.get("model") or agent_row.get("model") or "claude-sonnet-4-6").strip()
    config: dict[str, Any] = {
        "name": f"agent-{agent_row['id']}",
        "provider": provider,
        "agent_type": body.get("agent_type", "claude"),
        "model": model_name,
        "cwd": body.get("cwd", "/home/daytona"),
        "prompt": system_prompt,
        "shared_mounts": [str(workspace_id)],
        "pre_start_commands": [
            'apt-get update -qq && apt-get install -y -qq curl git ca-certificates '
            '&& curl -LsSf https://astral.sh/uv/install.sh | sh '
            '&& export PATH="$HOME/.local/bin:$PATH" '
            '&& UV_TOOL_BIN_DIR=/usr/local/bin uv tool install --reinstall '
            '"git+https://github.com/rllm-org/hive.git@staging" '
            '&& HOME=/root npx -y skills add rllm-org/hive#staging --all -g',
            f'mkdir -p /home/daytona && echo {base64.b64encode(system_prompt.encode()).decode()} '
            f'| base64 -d > /home/daytona/CLAUDE.md',
        ],
    }
    if global_volume_id:
        config["volume_id"] = global_volume_id
    if user_oauth_token:
        config["secrets"] = {**(config.get("secrets") or {}), "CLAUDE_CODE_OAUTH_TOKEN": user_oauth_token}
    if hive_server_url:
        config["mcp_servers"] = {
            "hive": {"type": "http", "url": f"{hive_server_url.rstrip('/')}/api/mcp"},
        }
    upstream = await sdk.create_session(**config)
    session_id = upstream.get("session_id") or upstream.get("id")
    if not session_id:
        raise HTTPException(502, f"agent-sdk returned incomplete session: {upstream}")

    return session_id


async def delete_agent_session(session_id: str | None) -> None:
    if not session_id:
        return
    try:
        await sdk.delete_session(session_id)
    except Exception as e:
        log.warning("delete_session %s failed: %s", session_id, e)
