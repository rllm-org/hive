import json
import os
import posixpath
from dataclasses import dataclass
from typing import Any

DEFAULT_EVAL_TIMEOUT = int(os.environ.get("VERIFY_EVAL_TIMEOUT", "300"))
DEFAULT_PREPARE_TIMEOUT = int(os.environ.get("VERIFY_PREPARE_TIMEOUT", "120"))
DEFAULT_STALE_AFTER = int(os.environ.get("VERIFY_STALE_AFTER", "1800"))
LOG_LIMIT = 10000

STATUS_NONE = "none"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"

TERMINAL_STATUSES = {STATUS_SUCCESS, STATUS_FAILED, STATUS_ERROR}


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    enabled: bool = False
    mutable_paths: tuple[str, ...] = ()
    prepare_timeout: int = DEFAULT_PREPARE_TIMEOUT
    eval_timeout: int = DEFAULT_EVAL_TIMEOUT

    @property
    def submission_status(self) -> str:
        return STATUS_PENDING if self.enabled else STATUS_NONE

    @property
    def score_field(self) -> str:
        return "verified_score" if self.enabled else "score"


def parse_task_config(raw: str | dict[str, Any] | None, *, strict: bool = False) -> dict[str, Any]:
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        if strict:
            raise ValueError("config must be a JSON object or JSON string")
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError("config must be valid JSON") from exc
        return {}
    if not isinstance(data, dict):
        if strict:
            raise ValueError("config must be a JSON object")
        return {}
    return dict(data)


def normalize_task_config(raw: str | dict[str, Any] | None) -> tuple[str | None, dict[str, Any], VerificationConfig]:
    if raw is None:
        return None, {}, VerificationConfig()

    data = parse_task_config(raw, strict=True)
    verification = verification_config_from_dict(data, strict=True)

    if "verify" in data:
        data["verify"] = verification.enabled
    if "mutable_paths" in data or verification.enabled:
        data["mutable_paths"] = list(verification.mutable_paths)
    if "prepare_timeout" in data:
        data["prepare_timeout"] = verification.prepare_timeout
    if "eval_timeout" in data:
        data["eval_timeout"] = verification.eval_timeout

    return json.dumps(data), data, verification


def verification_config_from_raw(raw: str | dict[str, Any] | None) -> VerificationConfig:
    return verification_config_from_dict(parse_task_config(raw), strict=False)


def verification_config_from_dict(data: dict[str, Any], *, strict: bool) -> VerificationConfig:
    verify = data.get("verify", False)
    if not isinstance(verify, bool):
        if strict:
            raise ValueError("config.verify must be a boolean")
        verify = bool(verify)

    prepare_timeout = _parse_timeout(
        data.get("prepare_timeout"),
        name="prepare_timeout",
        default=DEFAULT_PREPARE_TIMEOUT,
        strict=strict,
    )
    eval_timeout = _parse_timeout(
        data.get("eval_timeout"),
        name="eval_timeout",
        default=DEFAULT_EVAL_TIMEOUT,
        strict=strict,
    )
    mutable_paths = _parse_mutable_paths(data.get("mutable_paths"), strict=strict)

    if verify and not mutable_paths:
        if strict:
            raise ValueError("config.mutable_paths must contain at least one path when config.verify is true")
        verify = False

    return VerificationConfig(
        enabled=verify,
        mutable_paths=tuple(mutable_paths),
        prepare_timeout=prepare_timeout,
        eval_timeout=eval_timeout,
    )


def score_field(config: VerificationConfig) -> str:
    return config.score_field


async def recompute_task_stats(conn, task_id: str, config: VerificationConfig | None = None) -> None:
    if config is None:
        row = await (await conn.execute("SELECT config FROM tasks WHERE id = %s", (task_id,))).fetchone()
        config = verification_config_from_raw(row["config"] if row else None)

    run_score_field = score_field(config)
    row = await (await conn.execute(
        f"WITH ranked AS ("
        f"  SELECT id, created_at, {run_score_field} AS official_score,"
        f"         MAX({run_score_field}) OVER ("
        f"             ORDER BY created_at, id"
        f"             ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING"
        f"         ) AS prev_best"
        f"  FROM runs"
        f"  WHERE task_id = %s AND valid IS NOT FALSE AND {run_score_field} IS NOT NULL"
        f")"
        f" SELECT MAX(official_score) AS best_score,"
        f"        COUNT(*) FILTER (WHERE official_score > COALESCE(prev_best, '-Infinity'::float)) AS improvements"
        f" FROM ranked",
        (task_id,),
    )).fetchone()
    await conn.execute(
        "UPDATE tasks SET best_score = %s, improvements = %s WHERE id = %s",
        (row["best_score"], row["improvements"] or 0, task_id),
    )


def _parse_timeout(value: Any, *, name: str, default: int, strict: bool) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        if strict:
            raise ValueError(f"config.{name} must be a positive integer")
        return default
    return value


def _parse_mutable_paths(value: Any, *, strict: bool) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("config.mutable_paths must be a list of relative paths")
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            if strict:
                raise ValueError("config.mutable_paths must contain only strings")
            return []
        path = _normalize_mutable_path(item)
        if not path:
            if strict:
                raise ValueError("config.mutable_paths entries must not be empty")
            return []
        if path not in seen:
            normalized.append(path)
            seen.add(path)
    return normalized


def _normalize_mutable_path(path: str) -> str:
    raw = path.strip()
    if not raw:
        return ""
    parts = [part for part in raw.rstrip("/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return ""
    normalized = posixpath.normpath(raw.rstrip("/"))
    if normalized in {"", ".", ".."}:
        return ""
    if normalized.startswith("../") or raw.startswith("/") or normalized.startswith("/"):
        return ""
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        return ""
    return normalized
