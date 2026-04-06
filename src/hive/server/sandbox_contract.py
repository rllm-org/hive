"""Provider-neutral sandbox session contract: runtimes, auth modes, events, launch flags."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

ProviderId = Literal["claude_code", "codex", "opencode"]
AuthMode = Literal["browser_oauth", "device_code", "api_key", "auth_file"]
ApprovalMode = Literal["guarded", "auto_accept"]
SandboxStatus = Literal[
    "starting",
    "ready",
    "running",
    "stopping",
    "stopped",
    "failed",
]
SessionStatus = Literal["pending", "running", "interrupted", "completed", "failed"]


class SandboxEventType(str, Enum):
    SESSION_STARTED = "session.started"
    MESSAGE_USER = "message.user"
    MESSAGE_ASSISTANT = "message.assistant"
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_FINISHED = "tool.call.finished"
    PERMISSION_REQUESTED = "permission.requested"
    PERMISSION_RESOLVED = "permission.resolved"
    STDOUT_CHUNK = "stdout.chunk"
    STDERR_CHUNK = "stderr.chunk"
    SESSION_STATE_CHANGED = "session.state.changed"
    SESSION_COMPLETED = "session.completed"
    SESSION_FAILED = "session.failed"


@dataclass(frozen=True, slots=True)
class SessionLaunchSpec:
    """Normalized launch request mapped to provider CLIs inside the sandbox."""

    provider: ProviderId
    approval_mode: ApprovalMode
    cwd: str | None
    provider_options: dict[str, Any]

    def cli_extra_args(self) -> list[str]:
        """Extra argv for the coding agent when spawning (auto-approve modes)."""
        if self.approval_mode != "auto_accept":
            return []
        if self.provider == "claude_code":
            return ["--dangerously-skip-permissions"]
        if self.provider == "codex":
            return ["--full-auto"]
        if self.provider == "opencode":
            extra = self.provider_options.get("opencode_auto_args")
            if isinstance(extra, list) and all(isinstance(x, str) for x in extra):
                return list(extra)
            return []
        return []


def normalize_provider(value: str) -> ProviderId:
    v = value.strip().lower().replace("-", "_")
    if v in ("claude", "claude_code"):
        return "claude_code"
    if v == "codex":
        return "codex"
    if v in ("opencode", "open_code"):
        return "opencode"
    raise ValueError(f"unknown provider: {value}")


def normalize_approval_mode(value: str) -> ApprovalMode:
    v = value.strip().lower()
    if v in ("guarded", "default", "interactive"):
        return "guarded"
    if v in ("auto_accept", "auto", "full_auto", "yolo"):
        return "auto_accept"
    raise ValueError(f"unknown approval_mode: {value}")


def event_to_dict(offset: int, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"offset": offset, "type": event_type, "data": payload}
