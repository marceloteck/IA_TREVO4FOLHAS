from __future__ import annotations


def compute_reward_v2(
    hit_max: int,
    hits_distribution: dict,
    diversity: float,
    context: dict,
    decision: dict,
    stagnation: dict,
    cfg: dict,
) -> float:
    if not bool(cfg.get("enabled", True)):
        return float(context.get("legacy_reward", 0.0))

    weights = cfg.get("weights", {})
    w_hit = float(weights.get("hit_max", 1.0))
    w_dist = float(weights.get("distribution", 0.20))
    w_div = float(weights.get("diversity", 0.35))
    w_stag = float(weights.get("stagnation", 0.55))
    w_imp = float(weights.get("improve_bonus", 0.15))

    hit_scores = cfg.get("hit_scores", {})
    if int(hit_max) >= 15:
        hit_component = float(hit_scores.get("15", 3.0))
    elif int(hit_max) == 14:
        hit_component = float(hit_scores.get("14", 1.6))
    elif int(hit_max) == 13:
        hit_component = float(hit_scores.get("13", 0.35))
    elif int(hit_max) == 12:
        hit_component = float(hit_scores.get("12", 0.15))
    else:
        hit_component = float(hit_scores.get("11_or_less", -0.10))

    db = cfg.get("distribution_bonus", {})
    h13 = int(hits_distribution.get("13", 0))
    h12 = int(hits_distribution.get("12", 0))
    distribution = min(
        float(db.get("cap", 0.35)),
        h13 * float(db.get("13_each", 0.02)) + h12 * float(db.get("12_each", 0.01)),
    )

    diversity_cfg = context.get("diversity_cfg", {})
    min_div = float(diversity_cfg.get("min_diversity", 0.35))
    target_div = float(diversity_cfg.get("target_diversity", 0.55))
    bonus_scale = float(diversity_cfg.get("bonus_scale", 0.25))
    penalty_scale = float(diversity_cfg.get("penalty_scale", 0.60))
    if float(diversity) < min_div:
        diversity_component = -penalty_scale * (min_div - float(diversity))
    elif float(diversity) > target_div:
        diversity_component = bonus_scale * (float(diversity) - target_div)
    else:
        diversity_component = 0.0

    stag_score = float(stagnation.get("stagnation_score", 0.0))
    rescue_mode = bool(stagnation.get("rescue_mode", False))
    rescue_since = int(stagnation.get("rescue_since", 0))
    stagnation_component = -stag_score
    if rescue_mode and rescue_since >= int(context.get("rescue_penalty_after", 8)) and int(hit_max) < 14:
        stagnation_component -= 0.25

    baseline = float(context.get("recent_reward_baseline", 0.0))
    improve_component = 1.0 if float(context.get("legacy_reward", 0.0)) > baseline else 0.0

    reward = (
        w_hit * hit_component
        + w_dist * distribution
        + w_div * diversity_component
        + w_stag * stagnation_component
        + w_imp * improve_component
    )

    return float(reward)
