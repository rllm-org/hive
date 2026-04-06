"""Shared Daytona SDK helpers for verification and interactive task sandboxes."""

from __future__ import annotations

import asyncio
import importlib
import os
from typing import Any

try:
    try:
        _daytona = importlib.import_module("daytona_sdk")
    except ImportError:
        _daytona = importlib.import_module("daytona")
except ImportError:  # pragma: no cover
    AsyncDaytona = Any  # type: ignore[assignment, misc]
    CreateSandboxFromSnapshotParams = None  # type: ignore[assignment]
    VolumeMount = None  # type: ignore[assignment]
else:  # pragma: no branch
    AsyncDaytona = _daytona.AsyncDaytona  # type: ignore[attr-defined]
    CreateSandboxFromSnapshotParams = getattr(_daytona, "CreateSandboxFromSnapshotParams", None)
    VolumeMount = getattr(_daytona, "VolumeMount", None)

from .verification import VerificationConfig

AUTO_ARCHIVE_INTERVAL = int(os.environ.get("VERIFY_AUTO_ARCHIVE_INTERVAL", "60"))
AUTO_DELETE_INTERVAL = int(os.environ.get("VERIFY_AUTO_DELETE_INTERVAL", "120"))
SANDBOX_TIMEOUT = int(os.environ.get("VERIFY_SANDBOX_TIMEOUT", "120"))
VOLUME_TIMEOUT = int(os.environ.get("VERIFY_VOLUME_TIMEOUT", "120"))
DEFAULT_INTERACTIVE_SNAPSHOT = os.environ.get("HIVE_SANDBOX_SNAPSHOT", "hive-verify-python")


def resolve_env_vars_for_verification(config: VerificationConfig) -> dict[str, str]:
    env_vars = dict(config.sandbox.env)
    for env_name, ref in config.sandbox.secret_env:
        secret_name = f"HIVE_VERIFY_SECRET_{ref.upper()}"
        secret_value = os.environ.get(secret_name)
        if secret_value is None:
            raise RuntimeError(f"Missing verifier secret env {secret_name}")
        env_vars[env_name] = secret_value
    return env_vars


async def wait_for_volume_ready(daytona: Any, volume_name: str, *, timeout: int) -> Any:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        volume = await daytona.volume.get(volume_name)
        if str(volume.state).endswith("READY"):
            return volume
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"Timed out waiting for Daytona volume {volume_name} to become ready")
        await asyncio.sleep(1)


async def resolve_volume_mounts_for_verification(daytona: Any, config: VerificationConfig) -> list[Any]:
    if not config.sandbox.volumes:
        return []
    if VolumeMount is None:
        raise RuntimeError("Installed Daytona SDK does not expose VolumeMount")

    mounts: list[Any] = []
    for volume_config in config.sandbox.volumes:
        await daytona.volume.get(volume_config.name, create=True)
        volume = await wait_for_volume_ready(daytona, volume_config.name, timeout=VOLUME_TIMEOUT)
        mounts.append(
            VolumeMount(
                volume_id=volume.id,
                mount_path=volume_config.mount_path,
                subpath=volume_config.subpath,
            )
        )
    return mounts


async def create_sandbox_for_verification(daytona: Any, config: VerificationConfig) -> Any:
    if CreateSandboxFromSnapshotParams is None:
        raise RuntimeError("Installed Daytona SDK does not expose CreateSandboxFromSnapshotParams")

    env_vars = resolve_env_vars_for_verification(config)
    volumes = await resolve_volume_mounts_for_verification(daytona, config)
    params = CreateSandboxFromSnapshotParams(
        snapshot=config.sandbox.snapshot,
        auto_stop_interval=0,
        auto_archive_interval=AUTO_ARCHIVE_INTERVAL,
        auto_delete_interval=AUTO_DELETE_INTERVAL,
        env_vars=env_vars or None,
        volumes=volumes or None,
        network_block_all=config.sandbox.network_block_all,
        network_allow_list=config.sandbox.network_allow_list,
    )
    return await daytona.create(params, timeout=SANDBOX_TIMEOUT)


async def create_sandbox_interactive(
    daytona: Any,
    *,
    snapshot: str | None = None,
    env_vars: dict[str, str] | None = None,
    network_block_all: bool | None = None,
    network_allow_list: str | None = None,
) -> Any:
    """Create a sandbox for interactive coding agents (no task volume mounts by default)."""
    if CreateSandboxFromSnapshotParams is None:
        raise RuntimeError("Installed Daytona SDK does not expose CreateSandboxFromSnapshotParams")
    snap = (snapshot or DEFAULT_INTERACTIVE_SNAPSHOT).strip() or DEFAULT_INTERACTIVE_SNAPSHOT
    params = CreateSandboxFromSnapshotParams(
        snapshot=snap,
        auto_stop_interval=0,
        auto_archive_interval=AUTO_ARCHIVE_INTERVAL,
        auto_delete_interval=AUTO_DELETE_INTERVAL,
        env_vars=env_vars or None,
        volumes=None,
        network_block_all=network_block_all,
        network_allow_list=network_allow_list,
    )
    return await daytona.create(params, timeout=SANDBOX_TIMEOUT)
