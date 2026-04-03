"""Helpers for task verification config and official score bookkeeping."""

import json
import os
import posixpath
import re
from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_EVAL_TIMEOUT = int(os.environ.get("VERIFY_EVAL_TIMEOUT", "300"))
DEFAULT_PREPARE_TIMEOUT = int(os.environ.get("VERIFY_PREPARE_TIMEOUT", "120"))
DEFAULT_STALE_AFTER = int(os.environ.get("VERIFY_STALE_AFTER", "1800"))
DEFAULT_SANDBOX_SNAPSHOT = os.environ.get("VERIFY_DEFAULT_SNAPSHOT", "hive-verify-python")
LOG_LIMIT = 10000

STATUS_NONE = "none"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"

TERMINAL_STATUSES = {STATUS_SUCCESS, STATUS_FAILED, STATUS_ERROR}

VERIFICATION_MODE_ON_SUBMIT = "on_submit"
VERIFICATION_MODE_MANUAL = "manual"
SCORE_DIRECTION_MAXIMIZE = "maximize"
SCORE_DIRECTION_MINIMIZE = "minimize"
RESULT_FORMAT_STDOUT_KEYED = "stdout_keyed"
RESULT_FORMAT_STDOUT_LAST_FLOAT = "stdout_last_float"

PROTECTED_MUTABLE_PATH_PREFIXES = ("eval", ".git", ".hive")
PROTECTED_MUTABLE_PATHS = ("prepare.sh",)
SECRET_REF_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class SandboxVolumeConfig:
    """One verifier-managed Daytona volume mount."""

    name: str
    mount_path: str
    subpath: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the volume config for JSON storage."""

        data = {"name": self.name, "mount_path": self.mount_path}
        if self.subpath is not None:
            data["subpath"] = self.subpath
        return data


@dataclass(frozen=True, slots=True)
class SandboxPathLinkConfig:
    """One verifier-managed symlink from the task checkout into sandbox storage."""

    source_path: str
    target_path: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the runtime link config for JSON storage."""

        return {
            "source_path": self.source_path,
            "target_path": self.target_path,
        }


@dataclass(frozen=True, slots=True)
class SandboxConfig:
    """Normalized Daytona runtime settings for task verification."""

    snapshot: str = DEFAULT_SANDBOX_SNAPSHOT
    env: tuple[tuple[str, str], ...] = ()
    secret_env: tuple[tuple[str, str], ...] = ()
    env_file_path: str | None = None
    volumes: tuple[SandboxVolumeConfig, ...] = ()
    path_links: tuple[SandboxPathLinkConfig, ...] = ()
    network_block_all: bool | None = None
    network_allow_list: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the runtime config for JSON storage."""

        data: dict[str, Any] = {
            "snapshot": self.snapshot,
            "env": dict(self.env),
            "secret_env": dict(self.secret_env),
            "volumes": [volume.to_dict() for volume in self.volumes],
            "path_links": [path_link.to_dict() for path_link in self.path_links],
            "network_block_all": self.network_block_all,
            "network_allow_list": self.network_allow_list,
        }
        if self.env_file_path is not None:
            data["env_file_path"] = self.env_file_path
        return data


@dataclass(frozen=True, slots=True)
class VerificationConfig:
    """Normalized task-level verification settings."""

    enabled: bool = False
    verification_mode: Literal["on_submit", "manual"] = VERIFICATION_MODE_ON_SUBMIT
    mutable_paths: tuple[str, ...] = ()
    prepare_timeout: int = DEFAULT_PREPARE_TIMEOUT
    eval_timeout: int = DEFAULT_EVAL_TIMEOUT
    score_key: str = "score"
    direction: Literal["maximize", "minimize"] = SCORE_DIRECTION_MAXIMIZE
    result_format: Literal["stdout_keyed", "stdout_last_float"] = RESULT_FORMAT_STDOUT_KEYED
    sandbox: SandboxConfig = SandboxConfig()

    @property
    def queues_on_submit(self) -> bool:
        """Return whether submit should immediately queue this run."""

        return self.enabled and self.verification_mode == VERIFICATION_MODE_ON_SUBMIT

    @property
    def submission_status(self) -> str:
        """Return the run status assigned at submit time."""

        return STATUS_PENDING if self.queues_on_submit else STATUS_NONE

    @property
    def score_field(self) -> str:
        """Return the run column that counts as the task's official score."""

        return "verified_score" if self.enabled else "score"

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalized verification config for DB snapshots."""

        return {
            "verify": self.enabled,
            "verification_mode": self.verification_mode,
            "mutable_paths": list(self.mutable_paths),
            "prepare_timeout": self.prepare_timeout,
            "eval_timeout": self.eval_timeout,
            "score_key": self.score_key,
            "direction": self.direction,
            "result_format": self.result_format,
            "sandbox": self.sandbox.to_dict(),
        }


def parse_task_config(raw: str | dict[str, Any] | None, *, strict: bool = False) -> dict[str, Any]:
    """Parse a task config JSON blob into a dict."""

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
    """Validate and canonicalize task config before storing it."""

    if raw is None:
        return None, {}, VerificationConfig()

    data = parse_task_config(raw, strict=True)
    verification = verification_config_from_dict(data, strict=True)

    if _has_verification_settings(data) or verification.enabled:
        data.update(verification.to_dict())

    return json.dumps(data), data, verification


def verification_config_from_raw(raw: str | dict[str, Any] | None) -> VerificationConfig:
    """Build a normalized verification config from raw task config."""

    return verification_config_from_dict(parse_task_config(raw), strict=False)


def verification_config_from_dict(data: dict[str, Any], *, strict: bool) -> VerificationConfig:
    """Extract verification settings from a parsed task config dict."""

    verify = data.get("verify", False)
    if not isinstance(verify, bool):
        if strict:
            raise ValueError("config.verify must be a boolean")
        verify = bool(verify)

    verification_mode = _parse_verification_mode(data.get("verification_mode"), strict=strict, required=verify)
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
    score_key = _parse_score_key(data.get("score_key"), strict=strict, required=verify)
    direction = _parse_direction(data.get("direction"), strict=strict, required=verify)
    result_format = _parse_result_format(data.get("result_format"), strict=strict, required=verify)
    sandbox = _parse_sandbox_config(data.get("sandbox"), strict=strict, required=verify)

    if verify and not mutable_paths:
        if strict:
            raise ValueError("config.mutable_paths must contain at least one path when config.verify is true")
        verify = False

    return VerificationConfig(
        enabled=verify,
        verification_mode=verification_mode,
        mutable_paths=tuple(mutable_paths),
        prepare_timeout=prepare_timeout,
        eval_timeout=eval_timeout,
        score_key=score_key,
        direction=direction,
        result_format=result_format,
        sandbox=sandbox,
    )


def score_field(config: VerificationConfig) -> str:
    """Return the run column that counts as the task's official score."""

    return config.score_field


def normalize_verified_score(metric_value: float, config: VerificationConfig) -> float:
    """Convert a raw metric into the leaderboard's higher-is-better score."""

    if config.direction == SCORE_DIRECTION_MINIMIZE:
        return -metric_value
    return metric_value


async def recompute_task_stats(conn: Any, task_id: str, config: VerificationConfig | None = None) -> None:
    """Refresh task best-score and improvement counters from official run scores."""

    if config is None:
        row = await (await conn.execute("SELECT config FROM tasks WHERE id = %s", (task_id,))).fetchone()
        config = verification_config_from_raw(row["config"] if row else None)

    # Verified tasks rank by server-computed scores; legacy tasks still use self-reported scores.
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


def _has_verification_settings(data: dict[str, Any]) -> bool:
    """Return whether the task config contains verifier-owned settings."""

    return any(
        key in data
        for key in {
            "verify",
            "verification_mode",
            "mutable_paths",
            "prepare_timeout",
            "eval_timeout",
            "score_key",
            "direction",
            "result_format",
            "sandbox",
        }
    )


def _parse_timeout(value: Any, *, name: str, default: int, strict: bool) -> int:
    """Validate a positive timeout override, or fall back to the default."""

    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        if strict:
            raise ValueError(f"config.{name} must be a positive integer")
        return default
    return value


def _parse_verification_mode(
    value: Any,
    *,
    strict: bool,
    required: bool,
) -> Literal["on_submit", "manual"]:
    """Validate how verification jobs get queued."""

    if value is None:
        if strict and required:
            raise ValueError("config.verification_mode is required when config.verify is true")
        return VERIFICATION_MODE_ON_SUBMIT
    if value not in {VERIFICATION_MODE_ON_SUBMIT, VERIFICATION_MODE_MANUAL}:
        if strict:
            raise ValueError("config.verification_mode must be 'on_submit' or 'manual'")
        return VERIFICATION_MODE_ON_SUBMIT
    return value


def _parse_score_key(value: Any, *, strict: bool, required: bool) -> str:
    """Validate the raw metric key emitted by the canonical eval."""

    if value is None:
        if strict and required:
            raise ValueError("config.score_key is required when config.verify is true")
        return "score"
    if not isinstance(value, str) or not value.strip():
        if strict:
            raise ValueError("config.score_key must be a non-empty string")
        return "score"
    return value.strip()


def _parse_direction(
    value: Any,
    *,
    strict: bool,
    required: bool,
) -> Literal["maximize", "minimize"]:
    """Validate whether smaller or larger raw metrics are better."""

    if value is None:
        if strict and required:
            raise ValueError("config.direction is required when config.verify is true")
        return SCORE_DIRECTION_MAXIMIZE
    if value not in {SCORE_DIRECTION_MAXIMIZE, SCORE_DIRECTION_MINIMIZE}:
        if strict:
            raise ValueError("config.direction must be 'maximize' or 'minimize'")
        return SCORE_DIRECTION_MAXIMIZE
    return value


def _parse_result_format(
    value: Any,
    *,
    strict: bool,
    required: bool,
) -> Literal["stdout_keyed", "stdout_last_float"]:
    """Validate how the verifier should read the eval output."""

    if value is None:
        if strict and required:
            raise ValueError("config.result_format is required when config.verify is true")
        return RESULT_FORMAT_STDOUT_KEYED
    if value not in {RESULT_FORMAT_STDOUT_KEYED, RESULT_FORMAT_STDOUT_LAST_FLOAT}:
        if strict:
            raise ValueError("config.result_format must be 'stdout_keyed' or 'stdout_last_float'")
        return RESULT_FORMAT_STDOUT_KEYED
    return value


def _parse_sandbox_config(value: Any, *, strict: bool, required: bool) -> SandboxConfig:
    """Validate the Daytona runtime contract for verifier jobs."""

    if value is None:
        if strict and required:
            raise ValueError("config.sandbox is required when config.verify is true")
        return SandboxConfig()
    if not isinstance(value, dict):
        if strict:
            raise ValueError("config.sandbox must be an object")
        return SandboxConfig()

    snapshot = value.get("snapshot")
    if snapshot is None:
        if strict and required:
            raise ValueError("config.sandbox.snapshot is required when config.verify is true")
        snapshot = DEFAULT_SANDBOX_SNAPSHOT
    elif not isinstance(snapshot, str) or not snapshot.strip():
        if strict:
            raise ValueError("config.sandbox.snapshot must be a non-empty string")
        snapshot = DEFAULT_SANDBOX_SNAPSHOT
    else:
        snapshot = snapshot.strip()

    env = _parse_string_mapping(value.get("env"), field_name="config.sandbox.env", strict=strict)
    secret_env = _parse_secret_mapping(value.get("secret_env"), strict=strict)
    env_file_path = _parse_optional_relative_path(
        value.get("env_file_path"),
        field_name="config.sandbox.env_file_path",
        strict=strict,
    )
    volumes = _parse_volumes(value.get("volumes"), strict=strict)
    path_links = _parse_path_links(value.get("path_links"), strict=strict)
    network_block_all = _parse_optional_bool(
        value.get("network_block_all"),
        field_name="config.sandbox.network_block_all",
        strict=strict,
    )
    network_allow_list = _parse_optional_string(
        value.get("network_allow_list"),
        field_name="config.sandbox.network_allow_list",
        strict=strict,
    )

    return SandboxConfig(
        snapshot=snapshot,
        env=tuple(env.items()),
        secret_env=tuple(secret_env.items()),
        env_file_path=env_file_path,
        volumes=tuple(volumes),
        path_links=tuple(path_links),
        network_block_all=network_block_all,
        network_allow_list=network_allow_list,
    )


def _parse_string_mapping(value: Any, *, field_name: str, strict: bool) -> dict[str, str]:
    """Validate a string-to-string mapping."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        if strict:
            raise ValueError(f"{field_name} must be an object")
        return {}

    normalized: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            if strict:
                raise ValueError(f"{field_name} keys must be non-empty strings")
            return {}
        if not isinstance(item, str):
            if strict:
                raise ValueError(f"{field_name} values must be strings")
            return {}
        normalized[key.strip()] = item
    return normalized


def _parse_secret_mapping(value: Any, *, strict: bool) -> dict[str, str]:
    """Validate secret env var references."""

    secrets = _parse_string_mapping(value, field_name="config.sandbox.secret_env", strict=strict)
    for env_name, ref in secrets.items():
        if not SECRET_REF_RE.fullmatch(ref):
            if strict:
                raise ValueError(
                    f"config.sandbox.secret_env[{env_name!r}] must be a logical secret ref matching [A-Za-z0-9_]+"
                )
            return {}
    return secrets


def _parse_optional_relative_path(value: Any, *, field_name: str, strict: bool) -> str | None:
    """Validate an optional relative path inside the task repo."""

    if value is None:
        return None
    if not isinstance(value, str):
        if strict:
            raise ValueError(f"{field_name} must be a relative path string")
        return None

    normalized = _normalize_mutable_path(value)
    if not normalized:
        if strict:
            raise ValueError(f"{field_name} must be a relative path inside the task repo")
        return None
    return normalized


def _parse_optional_bool(value: Any, *, field_name: str, strict: bool) -> bool | None:
    """Validate an optional boolean task config field."""

    if value is None:
        return None
    if not isinstance(value, bool):
        if strict:
            raise ValueError(f"{field_name} must be a boolean")
        return None
    return value


def _parse_optional_string(value: Any, *, field_name: str, strict: bool) -> str | None:
    """Validate an optional non-empty string."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        if strict:
            raise ValueError(f"{field_name} must be a non-empty string")
        return None
    return value.strip()


def _parse_volumes(value: Any, *, strict: bool) -> list[SandboxVolumeConfig]:
    """Validate verifier-managed Daytona volume mounts."""

    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("config.sandbox.volumes must be a list")
        return []

    volumes: list[SandboxVolumeConfig] = []
    for item in value:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("config.sandbox.volumes entries must be objects")
            return []

        name = item.get("name")
        mount_path = item.get("mount_path")
        subpath = item.get("subpath")

        if not isinstance(name, str) or not name.strip():
            if strict:
                raise ValueError("config.sandbox.volumes entries require a non-empty string 'name'")
            return []
        normalized_mount_path = _normalize_mount_path(mount_path)
        if not normalized_mount_path:
            if strict:
                raise ValueError("config.sandbox.volumes entries require an absolute 'mount_path'")
            return []
        if subpath is not None and not isinstance(subpath, str):
            if strict:
                raise ValueError("config.sandbox.volumes[*].subpath must be a string when present")
            return []
        normalized_subpath = None
        if subpath is not None:
            normalized_subpath = _normalize_mutable_path(subpath)
            if not normalized_subpath:
                if strict:
                    raise ValueError("config.sandbox.volumes[*].subpath must be a relative path")
                return []

        volumes.append(
            SandboxVolumeConfig(
                name=name.strip(),
                mount_path=normalized_mount_path,
                subpath=normalized_subpath,
            )
        )
    return volumes


def _parse_path_links(value: Any, *, strict: bool) -> list[SandboxPathLinkConfig]:
    """Validate verifier-managed runtime symlinks into mounted sandbox paths."""

    if value is None:
        return []
    if not isinstance(value, list):
        if strict:
            raise ValueError("config.sandbox.path_links must be a list")
        return []

    path_links: list[SandboxPathLinkConfig] = []
    for item in value:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("config.sandbox.path_links entries must be objects")
            return []

        source_path = _normalize_mount_path(item.get("source_path"))
        if not source_path:
            if strict:
                raise ValueError("config.sandbox.path_links entries require an absolute 'source_path'")
            return []

        target_path = _parse_optional_relative_path(
            item.get("target_path"),
            field_name="config.sandbox.path_links[*].target_path",
            strict=strict,
        )
        if not target_path:
            return []
        if _is_protected_mutable_path(target_path):
            if strict:
                raise ValueError(
                    "config.sandbox.path_links cannot target protected verifier paths like eval/, prepare.sh, .git/, or .hive/"
                )
            return []

        path_links.append(
            SandboxPathLinkConfig(
                source_path=source_path,
                target_path=target_path,
            )
        )

    return path_links


def _parse_mutable_paths(value: Any, *, strict: bool) -> list[str]:
    """Validate the list of paths agents are allowed to override during verification."""

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
        if _is_protected_mutable_path(path):
            if strict:
                raise ValueError(
                    "config.mutable_paths cannot include protected verifier paths like eval/, prepare.sh, .git/, or .hive/"
                )
            return []
        if path not in seen:
            normalized.append(path)
            seen.add(path)
    return normalized


def _normalize_mutable_path(path: str) -> str:
    """Normalize a mutable path and reject absolute or parent-traversing values."""

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


def _normalize_mount_path(path: Any) -> str:
    """Normalize an absolute sandbox mount path."""

    if not isinstance(path, str):
        return ""
    raw = path.strip()
    if not raw.startswith("/"):
        return ""
    normalized = posixpath.normpath(raw)
    if normalized in {"", "/", ".", ".."}:
        return normalized if normalized == "/" else ""
    if not normalized.startswith("/") or any(part in {"", ".", ".."} for part in normalized.split("/")[1:]):
        return ""
    return normalized


def _is_protected_mutable_path(path: str) -> bool:
    """Return whether a mutable path would let agents overwrite verifier-owned files."""

    if path in PROTECTED_MUTABLE_PATHS:
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in PROTECTED_MUTABLE_PATH_PREFIXES)
