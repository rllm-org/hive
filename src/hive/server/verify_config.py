import json
from typing import Any


def parse_json_config(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def is_verify_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("verify"))


def validate_verify_task_config(cfg: dict[str, Any], has_eval_bundle: bool) -> None:
    if not cfg.get("verify"):
        return
    if not has_eval_bundle:
        raise ValueError("verify=true requires eval_bundle upload")
    art = cfg.get("artifact")
    if not isinstance(art, dict) or not art.get("required_paths"):
        raise ValueError("verify=true requires artifact.required_paths (array of relative paths)")
    paths = art["required_paths"]
    if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
        raise ValueError("artifact.required_paths must be a non-empty list of strings")
    se = cfg.get("server_eval")
    if not isinstance(se, dict):
        raise ValueError("verify=true requires server_eval object")
    if not se.get("command"):
        raise ValueError("server_eval.command is required")
    if not se.get("score_key"):
        raise ValueError("server_eval.score_key is required")
    direction = se.get("direction", "maximize")
    if direction not in ("maximize", "minimize"):
        raise ValueError("server_eval.direction must be 'maximize' or 'minimize'")
    result_format = se.get("result_format", "json")
    if result_format != "json":
        raise ValueError("only result_format=json is supported for now")


def merge_verify_into_config(base_json: str | None, verify_blob: str | None) -> dict[str, Any]:
    merged = parse_json_config(base_json)
    if verify_blob:
        v = parse_json_config(verify_blob)
        merged.update(v)
    return merged


def leaderboard_score_expr(verify: bool) -> str:
    if verify:
        return "COALESCE(r.verified_score, r.score)"
    return "r.score"


def best_score_expr_for_task(verify: bool) -> str:
    if verify:
        return "COALESCE(verified_score, score)"
    return "score"
