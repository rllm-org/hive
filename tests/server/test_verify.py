"""Tests for the training verification system."""

import hashlib
import io
import json
import os
import tarfile
import time

import pytest


def _register(client):
    resp = client.post("/api/register")
    assert resp.status_code == 201
    data = resp.json()
    return data["id"], data["token"]


def _create_task(client, task_id="test-task"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"hello"
        info = tarfile.TarInfo(name="README.md")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    resp = client.post(
        "/api/tasks",
        data={"id": task_id, "name": "Test Task", "description": "desc"},
        files={"archive": ("task.tar.gz", buf, "application/gzip")},
        headers={"X-Admin-Key": os.environ.get("ADMIN_KEY", "test-admin-key")},
    )
    assert resp.status_code == 201
    return task_id


def _fake_weights(content=b"fake-weights-data"):
    return hashlib.sha256(content).hexdigest(), content


class TestSeedRequest:
    def test_request_seed(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        assert resp.status_code == 201
        data = resp.json()
        assert "seed_id" in data
        assert "seed" in data
        assert "deadline" in data
        assert isinstance(data["seed"], int)

    def test_request_seed_invalid_task(self, client):
        agent_id, token = _register(client)
        resp = client.post("/api/tasks/nonexistent/verify/seed", params={"token": token})
        assert resp.status_code == 404

    def test_request_seed_expires_previous(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        resp1 = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id_1 = resp1.json()["seed_id"]

        resp2 = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id_2 = resp2.json()["seed_id"]
        assert seed_id_2 != seed_id_1

        # First seed should be expired
        status = client.get(f"/api/tasks/{task_id}/verify/{seed_id_1}", params={"token": token})
        assert status.json()["status"] == "expired"


class TestCheckpointCommit:
    def test_commit_checkpoints(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        h1, _ = _fake_weights(b"ckpt-0")
        h2, _ = _fake_weights(b"ckpt-1")
        body = {
            "seed_id": seed_id,
            "checkpoints": [
                {"sequence_num": 0, "weight_hash": h1, "reported_train_loss": None},
                {"sequence_num": 1, "weight_hash": h2, "reported_train_loss": 4.21},
            ],
        }
        resp = client.post(
            f"/api/tasks/{task_id}/verify/checkpoints",
            json=body, params={"token": token},
        )
        assert resp.status_code == 201
        assert resp.json()["committed"] == 2

    def test_commit_missing_fields(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.post(
            f"/api/tasks/{task_id}/verify/checkpoints",
            json={"seed_id": seed_id, "checkpoints": [{"sequence_num": 0}]},
            params={"token": token},
        )
        assert resp.status_code == 400

    def test_commit_wrong_agent(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        _, token2 = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        h, _ = _fake_weights()
        resp = client.post(
            f"/api/tasks/{task_id}/verify/checkpoints",
            json={"seed_id": seed_id, "checkpoints": [{"sequence_num": 0, "weight_hash": h}]},
            params={"token": token2},
        )
        assert resp.status_code == 404  # seed not found for this agent


class TestWeightUpload:
    def test_upload_final(self, client, monkeypatch, tmp_path):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        monkeypatch.setenv("HIVE_UPLOAD_DIR", str(tmp_path / "uploads"))
        # Reload the upload dir in verify module
        import hive.server.verify as v
        v.UPLOAD_DIR = str(tmp_path / "uploads")

        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        content = b"final-model-weights"
        expected_hash = hashlib.sha256(content).hexdigest()
        resp = client.post(
            f"/api/tasks/{task_id}/verify/upload",
            data={"seed_id": str(seed_id), "checkpoint_type": "final"},
            files={"weights": ("final.pt", io.BytesIO(content), "application/octet-stream")},
            params={"token": token},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["file_hash"] == expected_hash
        assert data["file_size"] == len(content)

    def test_upload_invalid_type(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.post(
            f"/api/tasks/{task_id}/verify/upload",
            data={"seed_id": str(seed_id), "checkpoint_type": "invalid"},
            files={"weights": ("w.pt", io.BytesIO(b"x"), "application/octet-stream")},
            params={"token": token},
        )
        assert resp.status_code == 400


class TestVerificationStatus:
    def test_status_after_seed(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.get(f"/api/tasks/{task_id}/verify/{seed_id}", params={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["checkpoints_committed"] == 0

    def test_status_wrong_agent(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        _, token1 = _register(client)
        _, token2 = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token1})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.get(f"/api/tasks/{task_id}/verify/{seed_id}", params={"token": token2})
        assert resp.status_code == 403


class TestChallenge:
    def test_challenge_picks_checkpoints(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        # Commit 5 checkpoints (0=init, 1-4 intermediate)
        ckpts = []
        for i in range(5):
            h, _ = _fake_weights(f"ckpt-{i}".encode())
            ckpts.append({"sequence_num": i, "weight_hash": h, "reported_train_loss": 4.0 - i * 0.5})
        client.post(
            f"/api/tasks/{task_id}/verify/checkpoints",
            json={"seed_id": seed_id, "checkpoints": ckpts},
            params={"token": token},
        )

        resp = client.post(
            f"/api/tasks/{task_id}/verify/{seed_id}/challenge",
            headers={"X-Admin-Key": "test-admin-key"},
        )
        assert resp.status_code == 200
        challenged = resp.json()["challenged_checkpoints"]
        assert len(challenged) == 2
        assert all(seq > 0 for seq in challenged)  # never picks init (seq 0)

    def test_challenge_requires_admin(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.post(
            f"/api/tasks/{task_id}/verify/{seed_id}/challenge",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert resp.status_code == 403


class TestSubmitWithSeedId:
    def test_submit_links_to_seed(self, client, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "test-admin-key")
        agent_id, token = _register(client)
        task_id = _create_task(client)

        seed_resp = client.post(f"/api/tasks/{task_id}/verify/seed", params={"token": token})
        seed_id = seed_resp.json()["seed_id"]

        resp = client.post(
            f"/api/tasks/{task_id}/submit",
            json={"sha": "abc123", "branch": "main", "tldr": "test", "message": "test",
                  "score": 1.5, "seed_id": seed_id},
            params={"token": token},
        )
        assert resp.status_code == 201

        # Verify seed is now linked
        status = client.get(f"/api/tasks/{task_id}/verify/{seed_id}", params={"token": token})
        assert status.json()["status"] == "submitted"
        assert status.json()["run_id"] == "abc123"


class TestHashVerification:
    def test_hash_match(self):
        from hive.server.verify_logic import compute_file_hash, verify_checkpoint_hash
        data = b"test-weights"
        h = compute_file_hash(data)
        assert verify_checkpoint_hash(data, h)
        assert not verify_checkpoint_hash(data, "wrong-hash")
