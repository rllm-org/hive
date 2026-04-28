"""Extract and store hidden eval bundles (local filesystem; Daytona hook later)."""

from __future__ import annotations

import hashlib
import io
import os
import tarfile
from pathlib import Path


def _eval_root() -> Path:
    return Path(os.environ.get("HIVE_EVAL_ROOT", "/tmp/hive_eval")).resolve()


def provision_eval_bundle(task_id: str, version: str, bundle_bytes: bytes) -> tuple[str, str]:
    """Unpack eval_bundle.tar.gz under HIVE_EVAL_ROOT. Returns (absolute_path_to_extract_root, sha256_hex)."""
    digest = hashlib.sha256(bundle_bytes).hexdigest()
    short = digest[:16]
    dest = _eval_root() / task_id / version / short
    dest.mkdir(parents=True, exist_ok=True)
    bio = io.BytesIO(bundle_bytes)
    with tarfile.open(fileobj=bio, mode="r:gz") as tf:
        tf.extractall(dest)
    return str(dest), digest
