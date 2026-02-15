from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import sqlite3
from typing import Any, Deque, Dict, List

from training.monitoring.baseline import compute_baseline_from_db


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
    def __init__(self, cfg: Dict[str, Any] | None = None, db_conn: sqlite3.Connection | None = None) -> None:
        self.cfg = dict(cfg or {})
        self.db_conn = db_conn
        self.enabled = bool(self.cfg.get("enabled", True))
        self.main_window = max(30, int(self.cfg.get("janela_principal", 300)))
        self.trend_window = max(10, int(self.cfg.get("janela_tendencia", 100)))
        self.min_outcomes_warmup = max(10, int(self.cfg.get("min_outcomes_para_sair_warmup", self.main_window)))
        self.margin = float(self.cfg.get("margem_baseline", 0.03))
        self.baseline_mode = str(self.cfg.get("baseline_mode", "soft") or "soft").strip().lower()
        if self.baseline_mode not in {"soft", "hard"}:
            self.baseline_mode = "soft"

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
        self._baseline_real_cache: Dict[str, float] | None = None
        self._baseline_real_source = "fixed"
        self._baseline_announced = False
        self._warmup_exit_announced = False

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

    def calcular_baseline_real(self, db: sqlite3.Connection | None, janela: int) -> Dict[str, float] | None:
        if db is None:
            return None
        min_samples = max(20, int(self.cfg.get("min_amostras_baseline_db", 60)))
        max_samples = max(min_samples + 1, int(self.cfg.get("max_amostras_baseline_db", 5000)))
        baseline_window = max(5, int(self.cfg.get("baseline_window_W", janela or self.main_window)))
        baseline = compute_baseline_from_db(
            db_path=db,
            n_min=min_samples,
            n_max=max_samples,
            window=baseline_window,
        )

        evaluated = int(baseline.get("num_outcomes", 0))
        if evaluated < min_samples:
            return {
                "frequencia_recente_q14_rate": 0.0,
                "copiar_ultimo_q14_rate": 0.0,
                "num_outcomes": evaluated,
                "source": "db_insufficient",
            }

        return {
            "frequencia_recente_q14_rate": _clamp(float(baseline.get("frequencia_recente_q14_rate", 0.0)), 0.0, 1.0),
            "copiar_ultimo_q14_rate": _clamp(float(baseline.get("copiar_ultimo_q14_rate", 0.0)), 0.0, 1.0),
            "num_outcomes": int(evaluated),
            "source": str(baseline.get("source", "db")),
        }

    def _resolve_baseline(self) -> Dict[str, float]:
        fixed_freq = self.baseline_freq_recent
        fixed_copy = self.baseline_copy_last
        baseline_fixed_ref = max(fixed_freq, fixed_copy)

        real = self.calcular_baseline_real(self.db_conn, self.main_window)
        if real is None or int(real.get("num_outcomes", 0)) <= 0:
            self._baseline_real_cache = None
            self._baseline_real_source = "fixed"
            return {
                "freq_recente_q14_rate": fixed_freq,
                "copiar_ultimo_q14_rate": fixed_copy,
                "ref_q14_rate": baseline_fixed_ref,
                "fixed_ref_q14_rate": baseline_fixed_ref,
                "real_ref_q14_rate": 0.0,
                "source": "fixed",
            }

        self._baseline_real_cache = dict(real)
        real_freq = float(real.get("frequencia_recente_q14_rate", 0.0))
        real_copy = float(real.get("copiar_ultimo_q14_rate", 0.0))
        real_ref = max(real_freq, real_copy)
        real_count = int(real.get("num_outcomes", 0))
        real_source_raw = str(real.get("source", "db"))
        if self.baseline_mode == "hard":
            ref = real_ref
            source = "db_hard"
        else:
            ref = max(baseline_fixed_ref, real_ref)
            source = "db_soft"
        self._baseline_real_source = source
        return {
            "freq_recente_q14_rate": fixed_freq,
            "copiar_ultimo_q14_rate": fixed_copy,
            "real_freq_recente_q14_rate": real_freq,
            "real_copiar_ultimo_q14_rate": real_copy,
            "ref_q14_rate": float(ref),
            "fixed_ref_q14_rate": float(baseline_fixed_ref),
            "real_ref_q14_rate": float(real_ref),
            "source": source,
            "real_num_outcomes": int(real_count),
            "real_source_raw": real_source_raw,
        }

    def _compute(self) -> Dict[str, Any]:
        data = list(self.history)
        n = len(data)
        events: List[str] = []

        baseline = self._resolve_baseline()
        baseline_ref = float(baseline.get("ref_q14_rate", max(self.baseline_freq_recent, self.baseline_copy_last)))
        baseline_source = str(baseline.get("source", "fixed"))
        if baseline_source == "fixed" and str(baseline.get("real_source_raw", "")).startswith("db_insufficient") and not self._baseline_announced:
            events.append(
                f"ℹ️ baseline_db: poucos dados ({int(baseline.get('real_num_outcomes', 0))}), usando baseline_fixo do JSON"
            )
            self._baseline_announced = True

        if baseline_source.startswith("db_") and not self._baseline_announced:
            events.append(
                "📊 Baseline real calculado via DB: "
                f"freq={float(baseline.get('real_freq_recente_q14_rate', 0.0)):.4f}, "
                f"copiar={float(baseline.get('real_copiar_ultimo_q14_rate', 0.0)):.4f}"
            )
            self._baseline_announced = True

        if n < self.trend_window:
            return {
                "status": STATUS_WARMUP,
                "sample_size": n,
                "metrics_main": self._window_metrics(data),
                "trend": {"delta_mean_hit": 0.0, "delta_q14_rate": 0.0, "delta_reward": 0.0},
                "baseline": {
                    **baseline,
                    "delta_q14_vs_baseline": 0.0,
                    "mode": self.baseline_mode,
                },
                "events": events,
            }

        main_slice = data[-self.main_window :]
        trend_slice = data[-self.trend_window :]
        main_m = self._window_metrics(main_slice)
        trend_m = self._window_metrics(trend_slice)

        delta_q14_vs_baseline = float(main_m["q14_rate"] - baseline_ref)
        trend = {
            "delta_mean_hit": float(trend_m["mean_hit"] - main_m["mean_hit"]),
            "delta_q14_rate": float(trend_m["q14_rate"] - main_m["q14_rate"]),
            "delta_reward": float(trend_m["reward_mean"] - main_m["reward_mean"]),
        }

        if n < self.min_outcomes_warmup:
            status = STATUS_WARMUP
        elif (
            delta_q14_vs_baseline > self.margin
            and main_m["reward_mean"] > self.reward_positive_limit
            and trend["delta_reward"] >= 0.0
            and trend["delta_q14_rate"] >= 0.0
        ):
            status = STATUS_LEARNING
        elif self.baseline_mode == "hard" and delta_q14_vs_baseline < -self.margin:
            status = STATUS_REGRESSING
        elif (
            delta_q14_vs_baseline < -self.margin
            and main_m["reward_mean"] < self.reward_negative_limit
            and (trend["delta_reward"] < 0.0 or trend["delta_q14_rate"] < 0.0)
        ):
            status = STATUS_REGRESSING
        else:
            status = STATUS_STABLE

        if status != STATUS_WARMUP and not self._warmup_exit_announced:
            events.append(f"🟢 Monitor saiu do WARMUP após {n} outcomes")
            self._warmup_exit_announced = True

        return {
            "status": status,
            "sample_size": n,
            "metrics_main": main_m,
            "trend": trend,
            "baseline": {
                **baseline,
                "delta_q14_vs_baseline": delta_q14_vs_baseline,
                "mode": self.baseline_mode,
            },
            "events": events,
        }

    def update(self, step: int, hit_max: int, reward: float, mode: str) -> Dict[str, Any]:
        if not self.enabled:
            return {
                "status": STATUS_STABLE,
                "step": int(step),
                "policy": self.policy.to_dict(),
                "should_log": False,
                "events": [],
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
            "warmup_exit_announced": bool(self._warmup_exit_announced),
            "baseline_announced": bool(self._baseline_announced),
        }

    def set_state(self, state: Dict[str, Any]) -> None:
        hist = list(state.get("history", []))
        self.history.clear()
        self.history.extend(hist[-self.history.maxlen :])
        self.green_counter = int(state.get("green_counter", 0))
        self.red_counter = int(state.get("red_counter", 0))
        self.last_status = str(state.get("last_status", STATUS_WARMUP))
        self.policy = MonitorPolicy.from_dict(dict(state.get("policy", {})))
        self._warmup_exit_announced = bool(state.get("warmup_exit_announced", False))
        self._baseline_announced = bool(state.get("baseline_announced", False))
