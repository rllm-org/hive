"""Lightweight MCP server for registering hive tools with agents.

Only handles tool registration (initialize + tools/list). Tool calls
return immediately — the actual interaction happens through the chat UI.
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

log = logging.getLogger("hive.mcp")

router = APIRouter(prefix="/api/mcp")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "ask_user",
        "description": (
            "Ask the user one or more questions. Each question has options for the user to choose from. "
            "You can ask multiple questions at once — they will be shown as a paginated form. "
            "Include 'Other...' as the last option to allow free-text input."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "description": "List of questions to ask. Each question is shown one at a time in a paginated widget.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question text",
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of options. Add 'Other...' as last option for custom input.",
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["select", "confirm", "multi_select", "text"],
                                "default": "select",
                                "description": "select: pick one, confirm: yes/no, multi_select: pick many, text: free input",
                            },
                        },
                        "required": ["question", "options"],
                    },
                },
            },
            "required": ["questions"],
        },
    },
]


# ---------------------------------------------------------------------------
# SSE endpoint (for MCP SSE transport)
# ---------------------------------------------------------------------------

@router.get("")
async def mcp_sse_endpoint(request: Request):
    """SSE stream with endpoint event for MCP SSE transport."""
    log.info("[mcp] GET SSE connect")
    async def sse_stream():
        yield "event: endpoint\ndata: /api/mcp\n\n"
        while True:
            yield ": heartbeat\n\n"
            await asyncio.sleep(15)
    return StreamingResponse(sse_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# JSON-RPC endpoint
# ---------------------------------------------------------------------------

@router.post("")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC — handles initialize and tools/list only."""
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    rpc_id = body.get("id")
    method = body.get("method", "")
    log.info("[mcp] %s (id=%s)", method, rpc_id)

    if method == "initialize":
        return _jsonrpc_ok(rpc_id, {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "hive", "version": "0.1.0"},
        })

    if method == "notifications/initialized":
        return JSONResponse(status_code=202, content={}, headers=_MCP_HEADERS)

    if method == "tools/list":
        return _jsonrpc_ok(rpc_id, {"tools": TOOLS})

    if method == "tools/call":
        # Tool calls are handled by the chat UI, not here.
        # Return immediately so the agent gets a response.
        return _jsonrpc_ok(rpc_id, {
            "content": [{"type": "text", "text": "Waiting for user response via chat."}],
        })

    return _jsonrpc_error(rpc_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

import uuid
_MCP_SESSION_ID = "hive-mcp-" + uuid.uuid4().hex[:12]
_MCP_HEADERS = {"mcp-session-id": _MCP_SESSION_ID}


def _jsonrpc_ok(rpc_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, headers=_MCP_HEADERS)


def _jsonrpc_error(rpc_id, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}, headers=_MCP_HEADERS)
