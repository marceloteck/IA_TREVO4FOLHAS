from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List


STATUS_WARMUP = "warmup"
STATUS_LEARNING = "learning"
STATUS_STABLE = "stable"
STATUS_REGRESSING = "regressing"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class MonitorPolicy:
    exploration_delta: float = 0.0
    confidence_mult: float = 1.0
    force_mode: str | None = None
    rescue_mode: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exploration_delta": float(self.exploration_delta),
            "confidence_mult": float(self.confidence_mult),
            "force_mode": self.force_mode,
            "rescue_mode": bool(self.rescue_mode),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MonitorPolicy":
        return cls(
            exploration_delta=float(data.get("exploration_delta", 0.0)),
            confidence_mult=float(data.get("confidence_mult", 1.0)),
            force_mode=data.get("force_mode"),
            rescue_mode=bool(data.get("rescue_mode", False)),
        )


class LearningMonitor:
    def __init__(self, cfg: Dict[str, Any] | None = None) -> None:
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.main_window = max(30, int(self.cfg.get("janela_principal", 300)))
        self.trend_window = max(10, int(self.cfg.get("janela_tendencia", 100)))
        self.margin = float(self.cfg.get("margem_baseline", 0.03))
        self.red_limit_steps = max(3, int(self.cfg.get("vermelho_limite_steps", 50)))
        self.green_strong_steps = max(5, int(self.cfg.get("verde_forte_steps", 100)))
        self.update_every_steps = max(1, int(self.cfg.get("update_every_steps", 10)))

        self.reward_negative_limit = float(self.cfg.get("reward_negativo_limite", -0.05))
        self.reward_positive_limit = float(self.cfg.get("reward_positivo_limite", 0.05))

        baseline_cfg = dict(self.cfg.get("baseline_fixo", {}))
        self.baseline_freq_recent = float(baseline_cfg.get("frequencia_recente_q14_rate", 0.10))
        self.baseline_copy_last = float(baseline_cfg.get("copiar_ultimo_q14_rate", 0.08))

        self.green_counter = 0
        self.red_counter = 0
        self.last_status = STATUS_WARMUP
        self.policy = MonitorPolicy()

        self.history: Deque[Dict[str, float]] = deque(maxlen=max(self.main_window * 3, 1200))

    def _window_metrics(self, data: List[Dict[str, float]]) -> Dict[str, float]:
        if not data:
            return {"mean_hit": 0.0, "q14_rate": 0.0, "q15_rate": 0.0, "reward_mean": 0.0}
        n = float(len(data))
        return {
            "mean_hit": sum(float(x.get("hit_max", 0.0)) for x in data) / n,
            "q14_rate": sum(1.0 for x in data if float(x.get("hit_max", 0.0)) >= 14.0) / n,
            "q15_rate": sum(1.0 for x in data if float(x.get("hit_max", 0.0)) >= 15.0) / n,
            "reward_mean": sum(float(x.get("reward", 0.0)) for x in data) / n,
        }

    def _compute(self) -> Dict[str, Any]:
        data = list(self.history)
        n = len(data)
        if n < self.trend_window:
            return {
                "status": STATUS_WARMUP,
                "sample_size": n,
                "metrics_main": self._window_metrics(data),
                "trend": {"delta_mean_hit": 0.0, "delta_q14_rate": 0.0, "delta_reward": 0.0},
                "baseline": {
                    "freq_recente_q14_rate": self.baseline_freq_recent,
                    "copiar_ultimo_q14_rate": self.baseline_copy_last,
                    "ref_q14_rate": max(self.baseline_freq_recent, self.baseline_copy_last),
                    "delta_q14_vs_baseline": 0.0,
                },
            }

        main_slice = data[-self.main_window :]
        trend_slice = data[-self.trend_window :]
        main_m = self._window_metrics(main_slice)
        trend_m = self._window_metrics(trend_slice)

        baseline_ref = max(self.baseline_freq_recent, self.baseline_copy_last)
        delta_q14_vs_baseline = float(main_m["q14_rate"] - baseline_ref)

        trend = {
            "delta_mean_hit": float(trend_m["mean_hit"] - main_m["mean_hit"]),
            "delta_q14_rate": float(trend_m["q14_rate"] - main_m["q14_rate"]),
            "delta_reward": float(trend_m["reward_mean"] - main_m["reward_mean"]),
        }

        if n < self.main_window:
            status = STATUS_WARMUP
        elif (
            delta_q14_vs_baseline > self.margin
            and main_m["reward_mean"] > self.reward_positive_limit
            and trend["delta_reward"] >= 0.0
            and trend["delta_q14_rate"] >= 0.0
        ):
            status = STATUS_LEARNING
        elif (
            main_m["reward_mean"] < self.reward_negative_limit
            and delta_q14_vs_baseline < -self.margin
            and (trend["delta_reward"] < 0.0 or trend["delta_q14_rate"] < 0.0)
        ):
            status = STATUS_REGRESSING
        else:
            status = STATUS_STABLE

        return {
            "status": status,
            "sample_size": n,
            "metrics_main": main_m,
            "trend": trend,
            "baseline": {
                "freq_recente_q14_rate": self.baseline_freq_recent,
                "copiar_ultimo_q14_rate": self.baseline_copy_last,
                "ref_q14_rate": baseline_ref,
                "delta_q14_vs_baseline": delta_q14_vs_baseline,
            },
        }

    def update(self, step: int, hit_max: int, reward: float, mode: str) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "status": STATUS_STABLE,
                "step": int(step),
                "policy": self.policy.to_dict(),
                "should_log": False,
            }

        self.history.append({"step": float(step), "hit_max": float(hit_max), "reward": float(reward)})
        snap = self._compute()

        status = str(snap.get("status", STATUS_STABLE))
        if status == STATUS_LEARNING:
            self.green_counter += 1
            self.red_counter = 0
        elif status == STATUS_REGRESSING:
            self.red_counter += 1
            self.green_counter = 0
        else:
            self.green_counter = max(0, self.green_counter - 1)
            self.red_counter = max(0, self.red_counter - 1)

        policy = MonitorPolicy()
        if status == STATUS_LEARNING and self.green_counter >= self.green_strong_steps:
            policy.exploration_delta = -float(self.cfg.get("green_exploration_decay", 0.05))
            policy.confidence_mult = 1.0 + float(self.cfg.get("green_confidence_boost", 0.08))
        elif status == STATUS_REGRESSING and self.red_counter >= self.red_limit_steps:
            policy.exploration_delta = float(self.cfg.get("red_exploration_boost", 0.12))
            policy.confidence_mult = 1.0 - float(self.cfg.get("red_confidence_reset", 0.20))
            policy.force_mode = "research"
            policy.rescue_mode = True

        policy.confidence_mult = _clamp(policy.confidence_mult, 0.20, 1.50)
        self.policy = policy
        self.last_status = status

        snap.update(
            {
                "step": int(step),
                "mode": str(mode),
                "status": status,
                "green_counter": int(self.green_counter),
                "red_counter": int(self.red_counter),
                "policy": self.policy.to_dict(),
                "should_log": int(step) % self.update_every_steps == 0,
            }
        )
        return snap

    def get_state(self) -> Dict[str, Any]:
        return {
            "history": list(self.history),
            "green_counter": int(self.green_counter),
            "red_counter": int(self.red_counter),
            "last_status": str(self.last_status),
            "policy": self.policy.to_dict(),
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        hist = list(state.get("history", []))
        self.history.clear()
        self.history.extend(hist[-self.history.maxlen :])
        self.green_counter = int(state.get("green_counter", 0))
        self.red_counter = int(state.get("red_counter", 0))
        self.last_status = str(state.get("last_status", STATUS_WARMUP))
        self.policy = MonitorPolicy.from_dict(dict(state.get("policy", {})))
