"""Define the Daytona snapshot profiles used by Hive verification.

This module is the single source of truth for the named snapshot profiles that
Hive's verifier expects. The seeding script creates these snapshots, 
and the calibration script smoke-tests them before a task is marked live 
for verification.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DAYTONA_SDK_SRC = Path(
    os.environ.get("DAYTONA_SDK_SRC", "~/daytona/libs/sdk-python/src")
).expanduser()

if str(DAYTONA_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(DAYTONA_SDK_SRC))

from daytona import Image, Resources  # type: ignore[import-not-found]


@dataclass(frozen=True, slots=True)
class SnapshotProfile:
    """A named verifier runtime profile and the task set it is intended to cover."""

    name: str
    description: str
    tasks: tuple[str, ...]
    resources: Resources
    build_image: Callable[[], Image]
    smoke_commands: tuple[str, ...]


def _python_image() -> Image:
    """Build the small Python baseline used for lightweight CPU/API-backed tasks."""

    return (
        Image.debian_slim("3.12")
        .run_commands(
            "apt-get update && apt-get install -y git bash curl",
            "mkdir -p /home/daytona/workspace",
        )
        .workdir("/home/daytona/workspace")
    )


def _python_large_image() -> Image:
    """Build the larger Python baseline for dataset-heavy verifier jobs."""

    return (
        Image.debian_slim("3.12")
        .run_commands(
            "apt-get update && apt-get install -y git bash curl unzip awscli",
            "mkdir -p /home/daytona/workspace",
        )
        .workdir("/home/daytona/workspace")
    )


def _ruby_yjit_image() -> Image:
    """Build the Ruby 3.4 + YJIT profile used by Shopify/Liquid tasks."""

    return (
        Image.base("ruby:3.4-slim-bookworm")
        .run_commands(
            "apt-get update && apt-get install -y git bash curl build-essential",
            "mkdir -p /home/daytona/workspace",
        )
        .env({"RUBY_YJIT_ENABLE": "1"})
        .workdir("/home/daytona/workspace")
    )


def _rust_chess_image() -> Image:
    """Build the Rust profile used for chess-engine verification."""

    return (
        Image.debian_slim("3.12")
        .run_commands(
            "apt-get update && apt-get install -y git bash curl build-essential rustc cargo stockfish",
            "mkdir -p /home/daytona/workspace",
        )
        .workdir("/home/daytona/workspace")
    )


def _dind_image() -> Image:
    """Build the Docker-in-Docker profile used for Terminal Bench tasks."""

    return (
        Image.base("docker:28.3.3-dind")
        .run_commands(
            "apk add --no-cache bash git curl python3 py3-pip openssh-client",
            "mkdir -p /home/daytona/workspace",
        )
        .workdir("/home/daytona/workspace")
    )


PROFILES: dict[str, SnapshotProfile] = {
    "hive-verify-python": SnapshotProfile(
        name="hive-verify-python",
        description="Small Python/API-backed verification profile.",
        tasks=("probe330a", "hello-world", "healthbench-lite", "babyvision-tiny", "arcagi2-tiny", "tau2"),
        resources=Resources(cpu=2, memory=4, disk=20),
        build_image=_python_image,
        smoke_commands=(
            "python3 --version",
            "git --version",
            "bash --version | head -n 1",
        ),
    ),
    "hive-verify-python-large": SnapshotProfile(
        name="hive-verify-python-large",
        description="Larger CPU profile for dataset-heavy verification.",
        tasks=("ptbxl-benchmark", "stanford-openvaccine"),
        resources=Resources(cpu=4, memory=8, disk=60),
        build_image=_python_large_image,
        smoke_commands=(
            "python3 --version",
            "python3 - <<'PY'\nimport os\nstat = os.statvfs('.')\nprint(int(stat.f_bavail * stat.f_frsize / (1024 * 1024 * 1024)))\nPY",
            "df -h .",
        ),
    ),
    "hive-verify-ruby-yjit": SnapshotProfile(
        name="hive-verify-ruby-yjit",
        description="Ruby 3.4 + YJIT profile for Liquid benchmarks.",
        tasks=("shopify-liquid-perf", "liquid-theme"),
        resources=Resources(cpu=2, memory=4, disk=20),
        build_image=_ruby_yjit_image,
        smoke_commands=(
            "ruby --version",
            "bundle --version",
            "ruby --yjit -e 'puts RubyVM::YJIT.enabled?'",
        ),
    ),
    "hive-verify-rust-chess": SnapshotProfile(
        name="hive-verify-rust-chess",
        description="Rust + Stockfish profile for chess engine evaluation.",
        tasks=("rust-chess-engine",),
        resources=Resources(cpu=4, memory=8, disk=30),
        build_image=_rust_chess_image,
        smoke_commands=(
            "rustc --version",
            "cargo --version",
            "/usr/games/stockfish bench 1",
        ),
    ),
    "hive-verify-dind": SnapshotProfile(
        name="hive-verify-dind",
        description="Docker-in-Docker profile for Terminal Bench verification.",
        tasks=("terminalbench-lite", "terminal-bench-hard"),
        resources=Resources(cpu=2, memory=4, disk=40),
        build_image=_dind_image,
        smoke_commands=(
            "python3 --version",
            "dockerd-entrypoint.sh >/tmp/dockerd.log 2>&1 &",
            (
                "sh -lc 'i=0; "
                "until docker info >/dev/null 2>&1; do "
                "i=$((i+1)); "
                "if [ \"$i\" -ge 60 ]; then echo \"dockerd failed\"; cat /tmp/dockerd.log; exit 1; fi; "
                "sleep 1; "
                "done'"
            ),
            "docker info",
        ),
    ),
}
