"""Daytona sandbox/volume integration (placeholder). Local bundle extraction when unset."""

from __future__ import annotations

import os

from .eval_bundle import provision_eval_bundle


def provision_eval_volume(task_id: str, version: str, bundle_bytes: bytes) -> tuple[str, str]:
    """Return (volume_id, bundle_sha256). volume_id embeds local path for dev."""
    if os.environ.get("DAYTONA_API_KEY"):
        raise RuntimeError(
            "Daytona provisioning is not implemented in this build. "
            "Unset DAYTONA_API_KEY to store eval bundles on the server filesystem (HIVE_EVAL_ROOT)."
        )
    path, sha = provision_eval_bundle(task_id, version, bundle_bytes)
    return f"local:{path}", sha
