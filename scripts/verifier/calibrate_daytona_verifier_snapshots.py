#!/usr/bin/env python3
"""Run smoke and calibration passes against Hive verifier snapshots.

Use this after seeding snapshots and before enabling a new verified task. It
can mount Daytona volumes and create task-local symlinks so calibration matches
the verifier's real runtime path for dataset-heavy tasks.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import posixpath
import shlex
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DAYTONA_SDK_SRC = Path(
    os.environ.get("DAYTONA_SDK_SRC", "~/daytona/libs/sdk-python/src")
).expanduser()

if str(DAYTONA_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(DAYTONA_SDK_SRC))

from daytona import (  # type: ignore[import-not-found]
    AsyncDaytona,
    CreateSandboxFromSnapshotParams,
    VolumeMount,
)
from daytona_verifier_profiles import PROFILES

VOLUME_TIMEOUT = 120


@dataclass(frozen=True, slots=True)
class CalibrationVolume:
    """One Daytona volume mount requested for a calibration run."""

    name: str
    mount_path: str
    subpath: str | None = None


@dataclass(frozen=True, slots=True)
class CalibrationPathLink:
    """One repo-relative symlink created before the calibration commands run."""

    target_path: str
    source_path: str


@dataclass(frozen=True, slots=True)
class CommandResult:
    """One calibration command result."""

    command: str
    exit_code: int
    seconds: float
    output: str


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Summary of one snapshot calibration run."""

    profile: str
    snapshot_id: str
    snapshot_image: str
    snapshot_cpu: float | int
    snapshot_memory: float | int
    snapshot_disk: float | int
    sandbox_id: str
    sandbox_snapshot: str | None
    sandbox_cpu: float | int
    sandbox_memory: float | int
    sandbox_disk: float | int
    workdir: str
    repo_path: str
    volumes: tuple[str, ...]
    path_links: tuple[str, ...]
    commands: tuple[CommandResult, ...]


def _parse_args() -> argparse.Namespace:
    """Parse the operator-facing CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILES),
        help="Snapshot profile to calibrate. Repeat to calibrate multiple profiles. Defaults to all profiles.",
    )
    parser.add_argument(
        "--repo-url",
        help="Optional git repo to clone inside the sandbox before running commands.",
    )
    parser.add_argument(
        "--commit",
        help="Optional commit SHA to check out when cloning --repo-url.",
    )
    parser.add_argument(
        "--clone-path",
        default="repo",
        help="Relative path under the sandbox workdir for the cloned repo. Default: repo",
    )
    parser.add_argument(
        "--command",
        action="append",
        help="Command to run inside the sandbox. Repeat to run multiple commands. Defaults to the profile smoke commands.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Environment variable override in KEY=VALUE form. Repeat to set multiple values.",
    )
    parser.add_argument(
        "--volume",
        action="append",
        default=[],
        help="Volume mount in NAME:MOUNT_PATH[:SUBPATH] form. Repeat to mount multiple volumes.",
    )
    parser.add_argument(
        "--path-link",
        action="append",
        default=[],
        help="Repo-relative symlink in TARGET_PATH=SOURCE_PATH form. Repeat to create multiple links.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-command timeout in seconds. Default: 600",
    )
    parser.add_argument(
        "--create-timeout",
        type=int,
        default=180,
        help="Sandbox creation timeout in seconds. Default: 180",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text.",
    )
    parser.add_argument(
        "--keep-sandbox",
        action="store_true",
        help="Leave sandboxes running for manual inspection instead of deleting them.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the built-in snapshot profiles and exit.",
    )
    return parser.parse_args()


def _parse_env(items: list[str]) -> dict[str, str]:
    """Parse repeated KEY=VALUE pairs into an env mapping."""

    env: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --env value {item!r}; expected KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --env value {item!r}; key must be non-empty")
        env[key] = value
    return env


def _parse_volumes(items: list[str]) -> list[CalibrationVolume]:
    """Parse repeated volume mount specs into structured calibration config."""

    volumes: list[CalibrationVolume] = []
    for item in items:
        parts = item.split(":", 2)
        if len(parts) < 2:
            raise ValueError(f"Invalid --volume value {item!r}; expected NAME:MOUNT_PATH[:SUBPATH]")

        name, mount_path = parts[0].strip(), parts[1].strip()
        subpath = parts[2].strip() if len(parts) == 3 else None

        if not name:
            raise ValueError(f"Invalid --volume value {item!r}; volume name must be non-empty")
        if not mount_path.startswith("/"):
            raise ValueError(f"Invalid --volume value {item!r}; mount path must be absolute")
        if subpath is not None:
            if not subpath or subpath.startswith("/"):
                raise ValueError(f"Invalid --volume value {item!r}; subpath must be a relative path when present")
            if any(part in {".", ".."} for part in subpath.split("/")):
                raise ValueError(f"Invalid --volume value {item!r}; subpath must be a relative path when present")

        volumes.append(CalibrationVolume(name=name, mount_path=posixpath.normpath(mount_path), subpath=subpath))
    return volumes


def _parse_path_links(items: list[str]) -> list[CalibrationPathLink]:
    """Parse repeated repo-local symlink specs into structured calibration config."""

    path_links: list[CalibrationPathLink] = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"Invalid --path-link value {item!r}; expected TARGET_PATH=SOURCE_PATH")

        target_path, source_path = item.split("=", 1)
        target_path = posixpath.normpath(target_path.strip())
        source_path = posixpath.normpath(source_path.strip())

        if target_path in {"", ".", ".."} or target_path.startswith("../") or target_path.startswith("/"):
            raise ValueError(f"Invalid --path-link value {item!r}; target path must be repo-relative")
        if not source_path.startswith("/"):
            raise ValueError(f"Invalid --path-link value {item!r}; source path must be absolute")

        path_links.append(CalibrationPathLink(target_path=target_path, source_path=source_path))
    return path_links


def _truncate_output(output: str, *, limit: int = 4000) -> str:
    """Keep calibration output readable without discarding the command result entirely."""

    output = output.strip()
    if len(output) <= limit:
        return output
    return output[:limit] + "\n...[truncated]..."


async def _run_command(
    sandbox: Any,
    command: str,
    *,
    cwd: str,
    env: dict[str, str],
    timeout: int,
) -> CommandResult:
    """Run one command inside the snapshot sandbox and record its duration."""

    started = time.perf_counter()
    result = await sandbox.process.exec(command, cwd=cwd, env=env or None, timeout=timeout)
    elapsed = time.perf_counter() - started
    return CommandResult(
        command=command,
        exit_code=result.exit_code,
        seconds=elapsed,
        output=_truncate_output(result.result or ""),
    )


async def _clone_repo_if_requested(
    sandbox: Any,
    *,
    workdir: str,
    repo_url: str | None,
    clone_path: str,
    commit: str | None,
) -> str:
    """Clone the requested repo into the sandbox and return the command cwd."""

    if not repo_url:
        return workdir

    repo_path = f"{workdir.rstrip('/')}/{clone_path.strip('/')}"
    await sandbox.git.clone(url=repo_url, path=repo_path, commit_id=commit)
    return repo_path


async def _resolve_volume_mounts(daytona: AsyncDaytona, volumes: list[CalibrationVolume]) -> list[VolumeMount]:
    """Resolve named Daytona volumes into sandbox mounts for calibration."""

    mounts: list[VolumeMount] = []
    for volume_config in volumes:
        await daytona.volume.get(volume_config.name, create=True)
        volume = await _wait_for_volume_ready(daytona, volume_config.name, timeout=VOLUME_TIMEOUT)
        mounts.append(
            VolumeMount(
                volume_id=volume.id,
                mount_path=volume_config.mount_path,
                subpath=volume_config.subpath,
            )
        )
    return mounts


async def _wait_for_volume_ready(daytona: AsyncDaytona, volume_name: str, *, timeout: int) -> Any:
    """Wait until a Daytona volume becomes mountable for calibration."""

    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        volume = await daytona.volume.get(volume_name)
        if str(volume.state).endswith("READY"):
            return volume
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"Timed out waiting for Daytona volume {volume_name} to become ready")
        await asyncio.sleep(1)


async def _materialize_path_links(
    sandbox: Any,
    *,
    repo_path: str,
    path_links: list[CalibrationPathLink],
    timeout: int,
) -> None:
    """Create task-local symlinks that point into mounted sandbox volumes."""

    for path_link in path_links:
        target = f"{repo_path.rstrip('/')}/{path_link.target_path}"
        parent = posixpath.dirname(target)

        result = await sandbox.process.exec(
            f"test ! -e {shlex.quote(target)}",
            cwd=repo_path,
            timeout=timeout,
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Calibration path link target already exists: {path_link.target_path}")

        if parent and parent != repo_path:
            result = await sandbox.process.exec(
                f"mkdir -p {shlex.quote(parent)}",
                cwd=repo_path,
                timeout=timeout,
            )
            if result.exit_code != 0:
                raise RuntimeError(f"Failed to create parent dir for calibration path link: {path_link.target_path}")

        result = await sandbox.process.exec(
            f"ln -s {shlex.quote(path_link.source_path)} {shlex.quote(target)}",
            cwd=repo_path,
            timeout=timeout,
        )
        if result.exit_code != 0:
            raise RuntimeError(f"Failed to create calibration path link: {path_link.target_path}")


async def _calibrate_profile(
    daytona: AsyncDaytona,
    profile_name: str,
    *,
    repo_url: str | None,
    commit: str | None,
    clone_path: str,
    commands: list[str] | None,
    env: dict[str, str],
    volumes: list[CalibrationVolume],
    path_links: list[CalibrationPathLink],
    timeout: int,
    create_timeout: int,
    keep_sandbox: bool,
) -> CalibrationResult:
    """Run the requested commands inside one named snapshot profile."""

    profile = PROFILES[profile_name]
    snapshot = await daytona.snapshot.get(profile.name)
    sandbox = None

    try:
        mounts = await _resolve_volume_mounts(daytona, volumes)
        sandbox = await daytona.create(
            CreateSandboxFromSnapshotParams(
                snapshot=profile.name,
                auto_stop_interval=0,
                auto_archive_interval=60,
                auto_delete_interval=120,
                volumes=mounts or None,
            ),
            timeout=create_timeout,
        )
        await sandbox.refresh_data()
        workdir = await sandbox.get_work_dir()
        repo_path = await _clone_repo_if_requested(
            sandbox,
            workdir=workdir,
            repo_url=repo_url,
            clone_path=clone_path,
            commit=commit,
        )
        if path_links:
            if not repo_url:
                raise ValueError("--path-link requires --repo-url so the repo-relative target exists")
            await _materialize_path_links(
                sandbox,
                repo_path=repo_path,
                path_links=path_links,
                timeout=timeout,
            )

        selected_commands = commands or list(profile.smoke_commands)
        results: list[CommandResult] = []

        for command in selected_commands:
            result = await _run_command(
                sandbox,
                command,
                cwd=repo_path,
                env=env,
                timeout=timeout,
            )
            results.append(result)
            if result.exit_code != 0:
                break

        return CalibrationResult(
            profile=profile.name,
            snapshot_id=snapshot.id,
            snapshot_image=snapshot.image_name,
            snapshot_cpu=snapshot.cpu,
            snapshot_memory=snapshot.mem,
            snapshot_disk=snapshot.disk,
            sandbox_id=sandbox.id,
            sandbox_snapshot=sandbox.snapshot,
            sandbox_cpu=sandbox.cpu,
            sandbox_memory=sandbox.memory,
            sandbox_disk=sandbox.disk,
            workdir=workdir,
            repo_path=repo_path,
            volumes=tuple(f"{volume.name}:{volume.mount_path}" for volume in volumes),
            path_links=tuple(f"{path_link.target_path} -> {path_link.source_path}" for path_link in path_links),
            commands=tuple(results),
        )
    finally:
        if sandbox is not None and not keep_sandbox:
            await daytona.delete(sandbox, timeout=60)


def _print_human(result: CalibrationResult) -> None:
    """Print one calibration result in a readable operator format."""

    print(f"\n==> {result.profile}")
    print(
        "    Snapshot resources:"
        f" cpu={result.snapshot_cpu} mem={result.snapshot_memory}GiB disk={result.snapshot_disk}GiB"
    )
    print(
        "    Sandbox resources:"
        f" cpu={result.sandbox_cpu} mem={result.sandbox_memory}GiB disk={result.sandbox_disk}GiB"
    )
    print(f"    Workdir: {result.workdir}")
    if result.repo_path != result.workdir:
        print(f"    Repo path: {result.repo_path}")
    if result.volumes:
        print(f"    Volumes: {', '.join(result.volumes)}")
    if result.path_links:
        print(f"    Path links: {', '.join(result.path_links)}")

    for command in result.commands:
        print(
            f"\n    $ {command.command}\n"
            f"    exit={command.exit_code} seconds={command.seconds:.2f}"
        )
        if command.output:
            indented = "\n".join(f"    {line}" for line in command.output.splitlines())
            print(indented)


async def _main() -> None:
    """Run the requested snapshot calibration passes."""

    args = _parse_args()
    if args.list:
        for profile in PROFILES.values():
            print(f"{profile.name}: {profile.description}")
            print(f"  tasks: {', '.join(profile.tasks)}")
        return

    selected = args.profile or list(PROFILES)
    env = _parse_env(args.env)
    volumes = _parse_volumes(args.volume)
    path_links = _parse_path_links(args.path_link)

    async with AsyncDaytona() as daytona:
        results: list[CalibrationResult] = []
        for profile_name in selected:
            result = await _calibrate_profile(
                daytona,
                profile_name,
                repo_url=args.repo_url,
                commit=args.commit,
                clone_path=args.clone_path,
                commands=args.command,
                env=env,
                volumes=volumes,
                path_links=path_links,
                timeout=args.timeout,
                create_timeout=args.create_timeout,
                keep_sandbox=args.keep_sandbox,
            )
            results.append(result)

    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
        return

    for result in results:
        _print_human(result)

    failures = [
        (result.profile, command.command, command.exit_code)
        for result in results
        for command in result.commands
        if command.exit_code != 0
    ]
    if failures:
        print("\nCalibration failures:")
        for profile, command, exit_code in failures:
            print(f"  - {profile}: exit {exit_code} from `{command}`")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(_main())
