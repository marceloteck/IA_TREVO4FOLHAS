from __future__ import annotations

REGIME_FRIO = 0
REGIME_ESTAVEL = 1
REGIME_AQUECIDO = 2
REGIME_INSTAVEL = 3


def detect_regime(context_features: dict, cfg: dict) -> int:
    if not bool(cfg.get("enabled", True)):
        return int(context_features.get("regime_id", REGIME_ESTAVEL))

    instability_cfg = cfg.get("instability", {})
    drift_thr = float(instability_cfg.get("drift_freq_120", 0.70))
    std_thr = float(instability_cfg.get("std_sum_120", 0.70))
    entropy_thr = float(instability_cfg.get("entropy_freq_120", 0.70))

    drift = float(context_features.get("drift_freq_120", 0.0))
    std = float(context_features.get("std_sum_120", 0.0))
    entropy = float(context_features.get("entropy_freq_120", 0.0))
    arm_reward = float(context_features.get("arm_recent_reward", 0.5))
    stagnation = float(context_features.get("stagnation_score", 0.0))

    if drift >= drift_thr or std >= std_thr or entropy >= entropy_thr:
        if bool(cfg.get("debug", False)):
            print("[regime] INSTAVEL por drift/std/entropy elevados")
        return REGIME_INSTAVEL

    reward_low = float(cfg.get("reward_low", 0.35))
    reward_high = float(cfg.get("reward_high", 0.60))

    if arm_reward <= reward_low and stagnation >= 0.5:
        if bool(cfg.get("debug", False)):
            print("[regime] FRIO por reward baixo e estagnação alta")
        return REGIME_FRIO

    if arm_reward >= reward_high and drift < drift_thr * 0.75:
        if bool(cfg.get("debug", False)):
            print("[regime] AQUECIDO por reward alto e drift controlado")
        return REGIME_AQUECIDO

    if bool(cfg.get("debug", False)):
        print("[regime] ESTAVEL por condição intermediária")
    return REGIME_ESTAVEL
