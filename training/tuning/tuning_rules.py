from __future__ import annotations


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def propose_changes(metrics: dict, current: dict, limits: dict) -> tuple[dict, str]:
    changes = {}
    reasons = []

    div_mean = float(metrics.get("diversity_mean", 0.0))
    fb = float(metrics.get("fallback_rate", 0.0))
    rescue_rate = float(metrics.get("rescue_rate", 0.0))
    step_sec = float(metrics.get("avg_step_seconds", 0.0))
    baseline_fail = bool(metrics.get("baseline_fail", False))

    if div_mean < 0.35:
        cur = float(current.get("reward_diversity_weight", 0.35))
        lo, hi = limits.get("reward_diversity_weight", [0.15, 0.60])
        changes.setdefault("reward_v2", {}).setdefault("weights", {})["diversity"] = clamp(cur + 0.02, lo, hi)
        cur_j = float(current.get("portfolio_max_clone_jaccard", 0.78))
        lo2, hi2 = limits.get("portfolio_max_clone_jaccard", [0.60, 0.85])
        changes.setdefault("portfolio", {}).setdefault("production", {})["max_clone_jaccard"] = clamp(cur_j - 0.01, lo2, hi2)
        reasons.append("low_diversity")

    if fb > 0.45:
        cur = float(current.get("confidence_threshold", 0.55))
        lo, hi = limits.get("confidence_threshold", [0.45, 0.75])
        changes.setdefault("meta_controller", {})["confidence_threshold"] = clamp(cur - 0.01, lo, hi)
        reasons.append("high_fallback")

    if rescue_rate > 0.25:
        cur = float(current.get("reward_stagnation_weight", 0.55))
        lo, hi = limits.get("reward_stagnation_weight", [0.25, 0.80])
        changes.setdefault("reward_v2", {}).setdefault("weights", {})["stagnation"] = clamp(cur + 0.02, lo, hi)
        reasons.append("high_rescue")

    if step_sec > 1.2:
        pair = int(current.get("pair_sample_max", 200))
        changes.setdefault("diversity", {})["pair_sample_max"] = max(80, pair - 20)
        reasons.append("high_step_cost")

    if baseline_fail:
        changes.setdefault("validator", {})["sample_concursos"] = int(current.get("sample_concursos", 20)) + 2
        reasons.append("baseline_fail_guard")

    return changes, ",".join(reasons) if reasons else "no_change"
