import io
import json
import tarfile

import pytest


def _minimal_task_tar():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in [
            ("program.md", b"# t\n"),
            ("eval/eval.sh", b"#!/bin/sh\necho ok\n"),
            ("prepare.sh", b"#!/bin/sh\n"),
        ]:
            ti = tarfile.TarInfo(name)
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))
    return buf.getvalue()


def _eval_bundle_tar():
    server_eval = b'''import json
print(json.dumps({"mae": 0.5, "neg_mae": -0.5}))
'''
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in [
            ("server_eval.py", server_eval),
            ("hidden/actuals.csv", b"a,b\n"),
        ]:
            ti = tarfile.TarInfo(name)
            ti.size = len(content)
            tar.addfile(ti, io.BytesIO(content))
    return buf.getvalue()


def test_create_verified_task_requires_bundle(client, monkeypatch, tmp_path):
    task_tar = _minimal_task_tar()
    vcfg = {
        "verify": True,
        "artifact": {"required_paths": ["artifacts/predictions.csv"]},
        "server_eval": {"command": "python3 server_eval.py", "score_key": "neg_mae", "direction": "maximize"},
    }
    resp = client.post(
        "/api/tasks",
        data={
            "id": "vt-no-bundle",
            "name": "VT",
            "description": "d",
            "verify_config": json.dumps(vcfg),
        },
        files={"archive": ("t.tar.gz", task_tar, "application/gzip")},
        headers={"X-Admin-Key": "test-key"},
    )
    assert resp.status_code == 400


def test_create_verified_task_atomic_and_submit_verifies(client, monkeypatch, tmp_path):
    monkeypatch.setenv("HIVE_EVAL_ROOT", str(tmp_path / "eval"))
    monkeypatch.setenv("HIVE_ARTIFACT_ROOT", str(tmp_path / "art"))
    task_tar = _minimal_task_tar()
    bundle = _eval_bundle_tar()
    vcfg = {
        "verify": True,
        "artifact": {"required_paths": ["artifacts/predictions.csv"], "max_size_mb": 5},
        "server_eval": {
            "volume_version": "v1",
            "command": "python3 server_eval.py",
            "score_key": "neg_mae",
            "direction": "maximize",
        },
    }
    resp = client.post(
        "/api/tasks",
        data={
            "id": "vt-ok",
            "name": "VT",
            "description": "d",
            "verify_config": json.dumps(vcfg),
        },
        files={
            "archive": ("t.tar.gz", task_tar, "application/gzip"),
            "eval_bundle": ("eval.tar.gz", bundle, "application/gzip"),
        },
        headers={"X-Admin-Key": "test-key"},
    )
    assert resp.status_code == 201, resp.text
    r = client.post("/api/register")
    token = r.json()["token"]
    aid = r.json()["id"]
    pred = b"a,b,c\n"
    resp = client.post(
        "/api/tasks/vt-ok/submit",
        data={
            "sha": "abc123def4567890123456789abcdef01234567",
            "branch": "main",
            "tldr": "t",
            "message": "m",
            "score": "0.9",
            "parent_id": "",
        },
        files={"artifacts/predictions.csv": ("predictions.csv", io.BytesIO(pred), "text/csv")},
        headers={"X-Agent-Token": token},
    )
    assert resp.status_code == 201, resp.text
    row = resp.json()["run"]
    assert row["verification_status"] in ("pending", "running", "success", "failed", "error")
    import time
    for _ in range(50):
        rr = client.get(f"/api/tasks/vt-ok/runs/{row['id']}", headers={"X-Agent-Token": token})
        if rr.json().get("verification_status") == "success":
            assert rr.json().get("verified_score") is not None
            return
        if rr.json().get("verification_status") in ("failed", "error"):
            pytest.fail(f"verify failed: {rr.json()}")
        time.sleep(0.05)
    pytest.fail("verification did not complete")

