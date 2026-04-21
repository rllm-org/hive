"""Lightweight MCP server for registering hive tools with agents.

Handles tool registration (initialize + tools/list). Tool calls for
ask_user return immediately — the agent is instructed to stop and wait
for the user's response as the next message.
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

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
            "Include 'Other...' as the last option to allow free-text input. "
            "IMPORTANT: After calling this tool, you MUST stop generating and wait. "
            "Do not write anything else. The user's answer will arrive as your next message."
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
    print("[mcp] GET SSE connect", flush=True)
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
    """MCP JSON-RPC — handles initialize, tools/list, and tools/call."""
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    rpc_id = body.get("id")
    method = body.get("method", "")
    print(f"[mcp] {method} (id={rpc_id})", flush=True)

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
        params = body.get("params", {})
        tool_name = params.get("name", "")
        print(f"[mcp] tools/call: {tool_name}", flush=True)

        if tool_name == "ask_user":
            return _jsonrpc_ok(rpc_id, {
                "content": [{"type": "text", "text": "Waiting for user response. Stop generating now."}],
            })

        return _jsonrpc_ok(rpc_id, {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
        })

    return _jsonrpc_error(rpc_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MCP_SESSION_ID = "hive-mcp-" + uuid.uuid4().hex[:12]
_MCP_HEADERS = {"mcp-session-id": _MCP_SESSION_ID}


def _jsonrpc_ok(rpc_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result}, headers=_MCP_HEADERS)


def _jsonrpc_error(rpc_id, code, message):
    return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}, headers=_MCP_HEADERS)
