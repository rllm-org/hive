#!/usr/bin/env python3
"""Create the Daytona snapshots that Hive's verifier worker expects.

Use when a new verified task needs one of the named snapshot profiles seeded 
in Daytona, or when the profile definitions change and the snapshots need to 
be updated.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

DAYTONA_SDK_SRC = Path(
    os.environ.get("DAYTONA_SDK_SRC", "~/daytona/libs/sdk-python/src")
).expanduser()

if str(DAYTONA_SDK_SRC) not in sys.path:
    sys.path.insert(0, str(DAYTONA_SDK_SRC))

from daytona import AsyncDaytona, CreateSnapshotParams  # type: ignore[import-not-found]
from daytona.common.sandbox import Resources  # type: ignore[import-not-found]
from daytona_verifier_profiles import PROFILES, SnapshotProfile


def _parse_args() -> argparse.Namespace:
    """Parse the operator-facing CLI arguments."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        action="append",
        choices=sorted(PROFILES),
        help="Snapshot profile to seed. Repeat to seed multiple profiles. Defaults to all profiles.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete an existing snapshot with the same name before recreating it.",
    )
    parser.add_argument(
        "--region-id",
        default=None,
        help="Optional Daytona region id for snapshot creation.",
    )
    parser.add_argument("--cpu", type=int, help="Override CPU for all selected profiles.")
    parser.add_argument("--memory", type=int, help="Override memory (GiB) for all selected profiles.")
    parser.add_argument("--disk", type=int, help="Override disk (GiB) for all selected profiles.")
    parser.add_argument("--gpu", type=int, help="Override GPU count for all selected profiles.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List the built-in snapshot profiles and exit.",
    )
    return parser.parse_args()


def _profile_resources(profile: SnapshotProfile, args: argparse.Namespace) -> Resources:
    """Apply optional operator overrides without mutating the canonical profile."""

    return Resources(
        cpu=args.cpu if args.cpu is not None else profile.resources.cpu,
        memory=args.memory if args.memory is not None else profile.resources.memory,
        disk=args.disk if args.disk is not None else profile.resources.disk,
        gpu=args.gpu if args.gpu is not None else profile.resources.gpu,
    )


async def _delete_existing_snapshot(daytona: AsyncDaytona, name: str) -> None:
    """Delete an existing snapshot by name if it is present."""

    try:
        snapshot = await daytona.snapshot.get(name)
    except Exception:
        return
    await daytona.snapshot.delete(snapshot)


async def _seed_profile(
    daytona: AsyncDaytona,
    profile: SnapshotProfile,
    *,
    args: argparse.Namespace,
    replace_existing: bool,
    region_id: str | None,
) -> None:
    """Create one named snapshot profile."""

    if replace_existing:
        await _delete_existing_snapshot(daytona, profile.name)

    resources = _profile_resources(profile, args)

    print(f"\n==> Seeding {profile.name}")
    print(f"    {profile.description}")
    print(f"    Tasks: {', '.join(profile.tasks)}")
    print(
        "    Resources:"
        f" cpu={resources.cpu} memory={resources.memory}GiB"
        f" disk={resources.disk}GiB gpu={resources.gpu or 0}"
    )

    await daytona.snapshot.create(
        CreateSnapshotParams(
            name=profile.name,
            image=profile.build_image(),
            resources=resources,
            region_id=region_id,
        ),
        on_logs=print,
    )


async def _main() -> None:
    """Seed the requested snapshot profiles."""

    args = _parse_args()
    if args.list:
        for profile in PROFILES.values():
            print(f"{profile.name}: {profile.description}")
            print(f"  tasks: {', '.join(profile.tasks)}")
        return

    selected = args.profile or list(PROFILES)
    async with AsyncDaytona() as daytona:
        for name in selected:
            await _seed_profile(
                daytona,
                PROFILES[name],
                args=args,
                replace_existing=args.replace_existing,
                region_id=args.region_id,
            )


if __name__ == "__main__":
    asyncio.run(_main())
