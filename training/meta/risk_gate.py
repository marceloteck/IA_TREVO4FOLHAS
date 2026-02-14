from __future__ import annotations

import math
from collections import deque
from typing import Any, Dict


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


class RiskGate:
    def __init__(self, cfg: dict | None = None):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.confidence_green = float(self.cfg.get("confidence_green", 0.65))
        self.confidence_red = float(self.cfg.get("confidence_red", 0.45))
        self.variance_weight = float(self.cfg.get("variance_weight", 0.25))
        self.trend_weight = float(self.cfg.get("trend_weight", 0.30))
        self.reward_weight = float(self.cfg.get("reward_weight", 0.30))
        self.delta14_weight = float(self.cfg.get("delta14_weight", 0.40))
        self.rewards = deque(maxlen=max(20, int(self.cfg.get("variance_window", 60))))

    @staticmethod
    def _sigmoid(x: float) -> float:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        z = math.exp(x)
        return z / (1.0 + z)

    def update(self, learning_snapshot: Dict[str, Any], reward: float) -> Dict[str, Any]:
        self.rewards.append(float(reward))
        if not self.enabled:
            return {
                "confidence_score": 0.5,
                "mode_risk": "balanceado",
                "modo_agressivo_producao": False,
                "exploration_delta": 0.0,
                "coverage_alpha_boost": 0.0,
            }

        base = dict(learning_snapshot.get("baseline", {}))
        trend = dict(learning_snapshot.get("trend", {}))
        metrics = dict(learning_snapshot.get("metrics_main", {}))

        delta14 = float(base.get("delta_q14_vs_baseline", 0.0))
        reward_mean = float(metrics.get("reward_mean", 0.0))
        trend_reward = float(trend.get("delta_reward", 0.0))

        n = len(self.rewards)
        if n <= 1:
            variance = 0.0
        else:
            mu = sum(self.rewards) / float(n)
            variance = sum((x - mu) ** 2 for x in self.rewards) / float(n)

        lin = (
            self.delta14_weight * (delta14 * 4.0)
            + self.reward_weight * reward_mean
            + self.trend_weight * (trend_reward * 2.0)
            - self.variance_weight * (variance * 3.0)
        )
        confidence = _clamp(self._sigmoid(lin), 0.0, 1.0)

        if confidence > self.confidence_green:
            mode = "PRODUCTION_AGRESSIVO"
            out = {
                "exploration_delta": -0.05,
                "coverage_alpha_boost": 0.0,
                "modo_agressivo_producao": True,
            }
        elif confidence <= self.confidence_red:
            mode = "DEFENSIVO"
            out = {
                "exploration_delta": +0.08,
                "coverage_alpha_boost": +0.15,
                "modo_agressivo_producao": False,
            }
        else:
            mode = "BALANCEADO"
            out = {
                "exploration_delta": 0.0,
                "coverage_alpha_boost": 0.05,
                "modo_agressivo_producao": False,
            }

        return {
            "confidence_score": float(confidence),
            "mode_risk": mode,
            "delta_14_vs_baseline": float(delta14),
            "reward_medio_recente": float(reward_mean),
            "variancia_reward": float(variance),
            "tendencia": float(trend_reward),
            **out,
        }
