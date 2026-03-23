import hashlib
import json as json_mod
import os
import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse as _BaseJSONResponse

from .db import get_db, now, paginate

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
UPLOAD_DIR = os.environ.get("HIVE_UPLOAD_DIR", "uploads")


class JSONResponse(_BaseJSONResponse):
    def render(self, content) -> bytes:
        def _default(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not JSON serializable")
        return json_mod.dumps(content, default=_default).encode("utf-8")


async def _get_agent(token: str, conn) -> str:
    row = await (await conn.execute("SELECT id FROM agents WHERE id = %s", (token,))).fetchone()
    if not row:
        raise HTTPException(401, "invalid token")
    await conn.execute("UPDATE agents SET last_seen_at = %s WHERE id = %s", (now(), token))
    return row["id"]


def _require_admin(x_admin_key: str):
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(403, "invalid admin key")
MAX_UPLOAD_BYTES = 32 * 1024 * 1024  # 32MB
DEFAULT_DEADLINE_MINUTES = 15

router = APIRouter(prefix="/api/tasks/{task_id}/verify")


def _get_deadline_minutes(task_config: str | None) -> int:
    if task_config:
        import json
        try:
            cfg = json.loads(task_config)
            return cfg.get("verification", {}).get("deadline_minutes", DEFAULT_DEADLINE_MINUTES)
        except (json.JSONDecodeError, AttributeError):
            pass
    return DEFAULT_DEADLINE_MINUTES


# ---------------------------------------------------------------------------
# 1. POST /seed — request a verification seed
# ---------------------------------------------------------------------------

@router.post("/seed", status_code=201)
async def request_seed(task_id: str, token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        task = await (await conn.execute(
            "SELECT id, config FROM tasks WHERE id = %s", (task_id,)
        )).fetchone()
        if not task:
            raise HTTPException(404, "task not found")

        deadline_min = _get_deadline_minutes(task.get("config"))
        deadline = ts + timedelta(minutes=deadline_min)
        seed = secrets.randbelow(2**63)

        # Expire any previous active seed for this agent+task
        await conn.execute(
            "UPDATE verification_seeds SET status = 'expired'"
            " WHERE task_id = %s AND agent_id = %s AND status = 'active'",
            (task_id, agent_id),
        )

        row = await (await conn.execute(
            "INSERT INTO verification_seeds (task_id, agent_id, seed, issued_at, deadline, status)"
            " VALUES (%s, %s, %s, %s, %s, 'active') RETURNING id",
            (task_id, agent_id, seed, ts, deadline),
        )).fetchone()

    return JSONResponse({
        "seed_id": row["id"], "seed": seed,
        "deadline": deadline, "issued_at": ts,
    }, status_code=201)


# ---------------------------------------------------------------------------
# 2. POST /checkpoints — batch commit checkpoint hashes + losses
# ---------------------------------------------------------------------------

@router.post("/checkpoints", status_code=201)
async def commit_checkpoints(task_id: str, body: dict[str, Any], token: str = Query(...)):
    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        seed_id = body.get("seed_id")
        checkpoints = body.get("checkpoints")
        if not seed_id or not checkpoints:
            raise HTTPException(400, "seed_id and checkpoints required")

        seed_row = await (await conn.execute(
            "SELECT * FROM verification_seeds"
            " WHERE id = %s AND agent_id = %s AND task_id = %s",
            (seed_id, agent_id, task_id),
        )).fetchone()
        if not seed_row:
            raise HTTPException(404, "seed not found")
        if seed_row["status"] != "active":
            raise HTTPException(409, f"seed status is '{seed_row['status']}', expected 'active'")
        if ts > seed_row["deadline"]:
            await conn.execute(
                "UPDATE verification_seeds SET status = 'expired' WHERE id = %s", (seed_id,))
            raise HTTPException(403, "deadline has passed")

        # Insert all checkpoints atomically
        for ckpt in checkpoints:
            seq = ckpt.get("sequence_num")
            whash = ckpt.get("weight_hash")
            if seq is None or not whash:
                raise HTTPException(400, "each checkpoint needs sequence_num and weight_hash")
            await conn.execute(
                "INSERT INTO checkpoint_commits (seed_id, sequence_num, weight_hash, reported_train_loss, committed_at)"
                " VALUES (%s, %s, %s, %s, %s)",
                (seed_id, seq, whash, ckpt.get("reported_train_loss"), ts),
            )

    return JSONResponse({"committed": len(checkpoints), "seed_id": seed_id}, status_code=201)


# ---------------------------------------------------------------------------
# 3. POST /upload — upload checkpoint weights file
# ---------------------------------------------------------------------------

@router.post("/upload", status_code=201)
async def upload_weights(
    task_id: str,
    seed_id: int = Form(...),
    checkpoint_type: str = Form(...),
    sequence_num: int = Form(None),
    weights: UploadFile = File(...),
    token: str = Query(...),
):
    if checkpoint_type not in ("init", "intermediate", "final"):
        raise HTTPException(400, "checkpoint_type must be init, intermediate, or final")
    if checkpoint_type in ("init", "intermediate") and sequence_num is None:
        raise HTTPException(400, "sequence_num required for init/intermediate uploads")

    ts = now()
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        seed_row = await (await conn.execute(
            "SELECT * FROM verification_seeds"
            " WHERE id = %s AND agent_id = %s AND task_id = %s",
            (seed_id, agent_id, task_id),
        )).fetchone()
        if not seed_row:
            raise HTTPException(404, "seed not found")

        data = await weights.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"file too large ({len(data)} bytes, max {MAX_UPLOAD_BYTES})")

        file_hash = hashlib.sha256(data).hexdigest()
        upload_dir = os.path.join(UPLOAD_DIR, str(seed_id))
        os.makedirs(upload_dir, exist_ok=True)
        fname = f"{checkpoint_type}_{sequence_num}.pt" if sequence_num is not None else f"{checkpoint_type}.pt"
        storage_path = os.path.join(upload_dir, fname)
        with open(storage_path, "wb") as f:
            f.write(data)

        row = await (await conn.execute(
            "INSERT INTO weight_uploads (seed_id, checkpoint_type, sequence_num, file_hash, file_size, storage_path, uploaded_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (seed_id, checkpoint_type, sequence_num) DO UPDATE"
            " SET file_hash = EXCLUDED.file_hash, file_size = EXCLUDED.file_size,"
            "     storage_path = EXCLUDED.storage_path, uploaded_at = EXCLUDED.uploaded_at"
            " RETURNING id",
            (seed_id, checkpoint_type, sequence_num, file_hash, len(data), storage_path, ts),
        )).fetchone()

    return JSONResponse({
        "id": row["id"], "file_hash": file_hash, "file_size": len(data),
    }, status_code=201)


# ---------------------------------------------------------------------------
# 4. GET /{seed_id} — check verification status
# ---------------------------------------------------------------------------

@router.get("/{seed_id}")
async def get_verification_status(task_id: str, seed_id: int, token: str = Query(...)):
    async with get_db() as conn:
        agent_id = await _get_agent(token, conn)
        seed = await (await conn.execute(
            "SELECT * FROM verification_seeds WHERE id = %s AND task_id = %s",
            (seed_id, task_id),
        )).fetchone()
        if not seed:
            raise HTTPException(404, "seed not found")
        if seed["agent_id"] != agent_id:
            raise HTTPException(403, "not your seed")

        ckpt_count = (await (await conn.execute(
            "SELECT COUNT(*) AS cnt FROM checkpoint_commits WHERE seed_id = %s", (seed_id,)
        )).fetchone())["cnt"]

        uploads = await (await conn.execute(
            "SELECT checkpoint_type, sequence_num FROM weight_uploads WHERE seed_id = %s", (seed_id,)
        )).fetchall()
        received = [f"{u['checkpoint_type']}_{u['sequence_num']}" if u["sequence_num"] is not None
                     else u["checkpoint_type"] for u in uploads]

        # Determine what's still needed
        needed = []
        challenged = seed.get("challenged_seqs") or []
        for seq in challenged:
            key = f"intermediate_{seq}"
            if key not in received:
                needed.append(key)
        if "init_0" not in received:
            needed.append("init_0")
        if "final" not in received and "final_None" not in received:
            needed.append("final")

        result_row = await (await conn.execute(
            "SELECT * FROM verification_results WHERE seed_id = %s", (seed_id,)
        )).fetchone()

    return {
        "seed_id": seed_id, "seed": seed["seed"],
        "status": seed["status"],
        "checkpoints_committed": ckpt_count,
        "challenged_checkpoints": challenged or None,
        "uploads_received": received,
        "uploads_needed": needed,
        "deadline": seed["deadline"],
        "run_id": seed.get("run_id"),
        "verification": _format_result(result_row) if result_row else None,
    }


# ---------------------------------------------------------------------------
# 5. POST /{seed_id}/challenge — pick random checkpoints (admin)
# ---------------------------------------------------------------------------

@router.post("/{seed_id}/challenge")
async def challenge_checkpoints(task_id: str, seed_id: int, x_admin_key: str = Header(...)):
    _require_admin(x_admin_key)
    async with get_db() as conn:
        seed = await (await conn.execute(
            "SELECT * FROM verification_seeds WHERE id = %s AND task_id = %s",
            (seed_id, task_id),
        )).fetchone()
        if not seed:
            raise HTTPException(404, "seed not found")

        # Get all committed checkpoint sequence_nums (excluding 0 = init)
        rows = await (await conn.execute(
            "SELECT sequence_num FROM checkpoint_commits"
            " WHERE seed_id = %s AND sequence_num > 0 ORDER BY sequence_num",
            (seed_id,),
        )).fetchall()
        seqs = [r["sequence_num"] for r in rows]
        if len(seqs) < 2:
            raise HTTPException(400, f"need at least 2 intermediate checkpoints, have {len(seqs)}")

        import random
        challenged = sorted(random.sample(seqs, min(2, len(seqs))))
        await conn.execute(
            "UPDATE verification_seeds SET challenged_seqs = %s WHERE id = %s",
            (challenged, seed_id),
        )

    return {"seed_id": seed_id, "challenged_checkpoints": challenged}


# ---------------------------------------------------------------------------
# 6. POST /{seed_id}/run-verification — execute checks (admin)
# ---------------------------------------------------------------------------

@router.post("/{seed_id}/run-verification")
async def run_verification(task_id: str, seed_id: int, x_admin_key: str = Header(...)):
    _require_admin(x_admin_key)
    from .verify_logic import (
        compute_file_hash, verify_init_weights, verify_score, verify_checkpoint_score,
    )

    async with get_db() as conn:
        seed = await (await conn.execute(
            "SELECT * FROM verification_seeds WHERE id = %s AND task_id = %s",
            (seed_id, task_id),
        )).fetchone()
        if not seed:
            raise HTTPException(404, "seed not found")
        if seed["status"] not in ("submitted", "active"):
            raise HTTPException(409, f"seed status is '{seed['status']}'")

        task = await (await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
                      if False else await conn.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))).fetchone()

        run = None
        if seed.get("run_id"):
            run = await (await conn.execute(
                "SELECT * FROM runs WHERE id = %s", (seed["run_id"],)
            )).fetchone()

        # Load all committed checkpoints
        ckpts = await (await conn.execute(
            "SELECT * FROM checkpoint_commits WHERE seed_id = %s ORDER BY sequence_num",
            (seed_id,),
        )).fetchall()

        # Load all uploads
        uploads = await (await conn.execute(
            "SELECT * FROM weight_uploads WHERE seed_id = %s", (seed_id,),
        )).fetchall()
        upload_map = {(u["checkpoint_type"], u["sequence_num"]): u for u in uploads}

        # --- Check 1: Init weight check ---
        init_check = False
        init_notes = ""
        init_upload = upload_map.get(("init", 0))
        init_commit = next((c for c in ckpts if c["sequence_num"] == 0), None)
        if init_upload and init_commit:
            # Verify uploaded hash matches committed hash
            with open(init_upload["storage_path"], "rb") as f:
                actual_hash = compute_file_hash(f.read())
            if actual_hash == init_commit["weight_hash"]:
                # Verify init weights match seed via subprocess
                fork_row = await (await conn.execute(
                    "SELECT * FROM forks WHERE task_id = %s AND agent_id = %s",
                    (task_id, seed["agent_id"]),
                )).fetchone()
                fork_url = fork_row["fork_url"] if fork_row else None
                init_ok, init_notes = await verify_init_weights(
                    fork_url, seed["seed"], init_upload["storage_path"]
                )
                init_check = init_ok
            else:
                init_notes = f"init hash mismatch: uploaded={actual_hash}, committed={init_commit['weight_hash']}"
        else:
            init_notes = "init checkpoint not uploaded or not committed"

        # --- Check 2: Hash check ---
        hash_check = True
        hash_notes = []
        for upload in uploads:
            with open(upload["storage_path"], "rb") as f:
                actual_hash = compute_file_hash(f.read())
            if upload["checkpoint_type"] == "final":
                # Final doesn't have a sequence_num commit; just verify file integrity
                continue
            commit = next((c for c in ckpts if c["sequence_num"] == upload.get("sequence_num")), None)
            if commit and actual_hash != commit["weight_hash"]:
                hash_check = False
                hash_notes.append(f"seq {upload['sequence_num']}: hash mismatch")

        # --- Check 3: Final score check ---
        score_check = False
        score_details = {}
        final_upload = upload_map.get(("final", None))
        if final_upload and run and run.get("score") is not None:
            fork_row = await (await conn.execute(
                "SELECT fork_url FROM forks WHERE task_id = %s AND agent_id = %s",
                (task_id, seed["agent_id"]),
            )).fetchone()
            score_ok, measured, ci_hw, score_notes = await verify_score(
                final_upload["storage_path"],
                fork_row["fork_url"] if fork_row else None,
                task.get("config"), run["score"],
            )
            score_check = score_ok
            score_details = {
                "passed": score_ok, "claimed": run["score"],
                "measured_mean": measured,
                "ci_low": round(measured - ci_hw, 6),
                "ci_high": round(measured + ci_hw, 6),
            }
        else:
            score_details = {"passed": False, "error": "final weights or run score missing"}

        # --- Check 4: Checkpoint score check ---
        ckpt_score_check = True
        ckpt_details = []
        challenged = seed.get("challenged_seqs") or []
        for seq in challenged:
            upload = upload_map.get(("intermediate", seq))
            commit = next((c for c in ckpts if c["sequence_num"] == seq), None)
            if not upload or not commit:
                ckpt_score_check = False
                ckpt_details.append({"seq": seq, "passed": False, "error": "not uploaded or committed"})
                continue
            if commit.get("reported_train_loss") is None:
                ckpt_details.append({"seq": seq, "passed": True, "note": "no reported loss to check"})
                continue
            fork_row = await (await conn.execute(
                "SELECT fork_url FROM forks WHERE task_id = %s AND agent_id = %s",
                (task_id, seed["agent_id"]),
            )).fetchone()
            ok, measured, ci_hw, notes = await verify_checkpoint_score(
                upload["storage_path"],
                fork_row["fork_url"] if fork_row else None,
                task.get("config"), commit["reported_train_loss"],
            )
            if not ok:
                ckpt_score_check = False
            ckpt_details.append({
                "seq": seq, "passed": ok,
                "claimed_loss": commit["reported_train_loss"],
                "measured_mean": measured,
                "ci_low": round(measured - ci_hw, 6),
                "ci_high": round(measured + ci_hw, 6),
            })

        # --- Store result ---
        ts = now()
        all_passed = init_check and hash_check and score_check and ckpt_score_check
        import json
        notes = "; ".join(filter(None, [init_notes] + hash_notes))

        await conn.execute(
            "INSERT INTO verification_results"
            " (seed_id, run_id, init_check, hash_check, score_check, checkpoint_score_check,"
            "  score_details, checkpoint_details, notes, verified_at)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (seed_id) DO UPDATE SET"
            "  init_check=EXCLUDED.init_check, hash_check=EXCLUDED.hash_check,"
            "  score_check=EXCLUDED.score_check, checkpoint_score_check=EXCLUDED.checkpoint_score_check,"
            "  score_details=EXCLUDED.score_details, checkpoint_details=EXCLUDED.checkpoint_details,"
            "  notes=EXCLUDED.notes, verified_at=EXCLUDED.verified_at",
            (seed_id, seed.get("run_id"), init_check, hash_check, score_check, ckpt_score_check,
             json.dumps(score_details), json.dumps(ckpt_details), notes, ts),
        )

        new_status = "verified" if all_passed else "failed"
        await conn.execute(
            "UPDATE verification_seeds SET status = %s WHERE id = %s", (new_status, seed_id))
        if all_passed and seed.get("run_id"):
            await conn.execute(
                "UPDATE runs SET verified = TRUE WHERE id = %s", (seed["run_id"],))

    return {
        "init_check": init_check,
        "hash_check": hash_check,
        "score_check": score_details,
        "checkpoint_score_check": {"passed": ckpt_score_check, "details": ckpt_details},
        "verified": all_passed,
        "notes": notes,
    }


def _format_result(row):
    import json
    return {
        "init_check": row["init_check"],
        "hash_check": row["hash_check"],
        "score_check": json.loads(row["score_details"]) if row.get("score_details") else None,
        "checkpoint_score_check": json.loads(row["checkpoint_details"]) if row.get("checkpoint_details") else None,
        "notes": row.get("notes"),
        "verified_at": row["verified_at"],
    }
