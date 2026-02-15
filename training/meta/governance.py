from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
import sqlite3
from typing import Any, Dict, List


@dataclass
class GovernanceInputs:
    status: str
    confidence_score: float | None
    delta14: float
    reward_avg: float
    trend: float
    structural_stagnation: bool
    clone_ratio: float
    entropy: float
    pair_coverage: float
    step: int
    run_id: int


@dataclass
class GovernanceDecision:
    policy_name: str
    max_games_mult: float
    pool_size_delta: int
    coverage_alpha: float
    min_pair_coverage: float
    max_clone_jaccard: float
    actions: List[str]
    reason: str


class GovernanceManager:
    def __init__(self, cfg: Dict[str, Any] | None = None) -> None:
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", False))
        env_toggle = str(os.getenv("GOVERNANCE", "")).strip()
        if env_toggle in {"0", "1"}:
            self.enabled = env_toggle == "1"
        self.history: Dict[str, Any] = {
            "green_streak": 0,
            "yellow_streak": 0,
            "red_streak": 0,
            "low_reward_streak": 0,
            "delta14_red_streak": 0,
            "total_updates": 0,
            "last_red_step": -1,
            "last_freeze_step": -10**9,
            "freeze_active_until_step": 0,
            # compatibilidade com código legado do backtest
            "autotuning_frozen_until_step": 0,
        }

    def get_state(self) -> Dict[str, Any]:
        return dict(self.history)

    def set_state(self, state: Dict[str, Any]) -> None:
        if not isinstance(state, dict):
            return
        self.history.update(
            {
                "green_streak": int(state.get("green_streak", self.history["green_streak"])),
                "yellow_streak": int(state.get("yellow_streak", self.history["yellow_streak"])),
                "red_streak": int(state.get("red_streak", self.history["red_streak"])),
                "low_reward_streak": int(state.get("low_reward_streak", self.history["low_reward_streak"])),
                "delta14_red_streak": int(state.get("delta14_red_streak", self.history["delta14_red_streak"])),
                "total_updates": int(state.get("total_updates", self.history["total_updates"])),
                "last_red_step": int(state.get("last_red_step", self.history["last_red_step"])),
                "last_freeze_step": int(state.get("last_freeze_step", self.history["last_freeze_step"])),
                "freeze_active_until_step": int(state.get("freeze_active_until_step", self.history["freeze_active_until_step"])),
                "autotuning_frozen_until_step": int(state.get("autotuning_frozen_until_step", self.history["autotuning_frozen_until_step"])),
            }
        )

    def _status_norm(self, status: str) -> str:
        s = str(status or "").strip().lower()
        return {
            "warmup": "WARMUP",
            "learning": "GREEN",
            "stable": "YELLOW",
            "regressing": "RED",
            "green": "GREEN",
            "yellow": "YELLOW",
            "red": "RED",
        }.get(s, "YELLOW")

    def _update_streaks(self, status: str, inputs: GovernanceInputs, rules: Dict[str, Any]) -> None:
        if status == "GREEN":
            self.history["green_streak"] = int(self.history.get("green_streak", 0)) + 1
            self.history["yellow_streak"] = 0
            self.history["red_streak"] = 0
        elif status == "RED":
            self.history["red_streak"] = int(self.history.get("red_streak", 0)) + 1
            self.history["green_streak"] = 0
            self.history["yellow_streak"] = 0
            self.history["last_red_step"] = int(inputs.step)
        elif status == "YELLOW":
            self.history["yellow_streak"] = int(self.history.get("yellow_streak", 0)) + 1
            self.history["green_streak"] = max(0, int(self.history.get("green_streak", 0)) - 1)
            self.history["red_streak"] = max(0, int(self.history.get("red_streak", 0)) - 1)
        else:
            self.history["green_streak"] = max(0, int(self.history.get("green_streak", 0)) - 1)
            self.history["red_streak"] = max(0, int(self.history.get("red_streak", 0)) - 1)

        if float(inputs.reward_avg) <= float(rules.get("true_red_reward_threshold", -0.30)):
            self.history["low_reward_streak"] = int(self.history.get("low_reward_streak", 0)) + 1
        else:
            self.history["low_reward_streak"] = 0

        if float(inputs.delta14) <= float(rules.get("delta14_red", -0.03)):
            self.history["delta14_red_streak"] = int(self.history.get("delta14_red_streak", 0)) + 1
        else:
            self.history["delta14_red_streak"] = 0

    def is_low_conf(self, inputs: GovernanceInputs, cfg: Dict[str, Any]) -> bool:
        if inputs.confidence_score is None:
            return False
        return float(inputs.confidence_score) < float(cfg.get("confidence_red", 0.45))

    def is_true_red(self, inputs: GovernanceInputs, cfg: Dict[str, Any], history: Dict[str, Any]) -> bool:
        status = self._status_norm(inputs.status)
        red_min = int(cfg.get("red_min_consecutive_updates", 3))

        if bool(cfg.get("true_red_requires_status_red", True)):
            return status == "RED" and int(history.get("red_streak", 0)) >= red_min

        reward_req = int(cfg.get("true_red_reward_requires_consecutive", 3))
        reward_red = int(history.get("low_reward_streak", 0)) >= reward_req
        delta_red = int(history.get("delta14_red_streak", 0)) >= red_min
        status_red = status == "RED" and int(history.get("red_streak", 0)) >= red_min
        return bool(status_red or reward_red or delta_red)

    def maybe_freeze(self, history: Dict[str, Any], cfg: Dict[str, Any], step: int) -> bool:
        freeze_steps = max(1, int(cfg.get("freeze_autotuning_steps", 500)))
        cooldown = max(0, int(cfg.get("freeze_cooldown_steps", 800)))

        freeze_active_until = int(history.get("freeze_active_until_step", 0))
        if int(step) < freeze_active_until:
            return False

        last_freeze_step = int(history.get("last_freeze_step", -10**9))
        if int(step) - last_freeze_step < cooldown:
            return False

        history["last_freeze_step"] = int(step)
        history["freeze_active_until_step"] = int(step) + freeze_steps
        history["autotuning_frozen_until_step"] = int(step) + freeze_steps
        return True

    def choose_policy(self, inputs: GovernanceInputs) -> GovernanceDecision:
        if not self.enabled:
            return GovernanceDecision(
                policy_name="NORMAL",
                max_games_mult=1.0,
                pool_size_delta=0,
                coverage_alpha=0.25,
                min_pair_coverage=0.30,
                max_clone_jaccard=0.75,
                actions=["GOVERNANCE_DISABLED"],
                reason="governance_disabled",
            )
        rules = dict(self.cfg.get("decision_rules", {}))
        anti = dict(self.cfg.get("anti_self_deception", {}))
        policies = dict(self.cfg.get("policies", {}))
        warmup_policy = str(rules.get("warmup_policy", "SAFE"))

        status = self._status_norm(inputs.status)
        self.history["total_updates"] = int(self.history.get("total_updates", 0)) + 1
        self._update_streaks(status=status, inputs=inputs, rules=rules)
        self.history["last_eval_step"] = int(inputs.step)

        conf = 0.5 if inputs.confidence_score is None else float(inputs.confidence_score)
        actions: List[str] = []
        reason = ""

        is_true_red_now = self.is_true_red(inputs=inputs, cfg=rules, history=self.history)
        is_low_conf_now = self.is_low_conf(inputs=inputs, cfg=rules)

        if status == "WARMUP":
            policy = warmup_policy
            actions = ["WARMUP_SAFE"]
            reason = "warmup_policy"
        elif bool(rules.get("structural_stagnation_forces_safe", True)) and bool(inputs.structural_stagnation):
            policy = "SAFE"
            actions = ["FORCE_SAFE_STAGNATION"]
            reason = "stagnation_safe"
        elif is_true_red_now:
            policy = "SAFE"
            actions = ["TRUE_RED_SAFE"]
            reason = "true_red_persistent"
        elif is_low_conf_now:
            policy = "SAFE"
            actions = ["LOW_CONF_DEFENSIVE"]
            reason = "low_conf_defensive"
        elif (
            status == "GREEN"
            and conf >= float(rules.get("confidence_green", 0.65))
            and float(inputs.delta14) >= float(rules.get("delta14_green", 0.03))
            and int(self.history.get("green_streak", 0)) >= int(rules.get("green_min_consecutive_updates", 3))
        ):
            policy = "AGGRESSIVE"
            reason = "green_confirmed"
        else:
            policy = "NORMAL"
            reason = "neutral_band"

        # anti autoengano
        if bool(anti.get("block_aggressive_on_true_red", True)):
            last_red = int(self.history.get("last_red_step", -1))
            if policy == "AGGRESSIVE" and last_red >= 0 and (int(inputs.step) - last_red) <= int(rules.get("red_min_consecutive_updates", 3)):
                policy = "NORMAL"
                actions.append("BLOCK_AGGRESSIVE_RECENT_TRUE_RED")
                reason = "neutral_band"

        min_updates = int(anti.get("min_updates_before_allow_aggressive", 10))
        if policy == "AGGRESSIVE" and int(self.history.get("total_updates", 0)) < min_updates:
            policy = "NORMAL"
            actions.append("BLOCK_AGGRESSIVE_MIN_UPDATES")
            reason = "neutral_band"

        if policy not in policies:
            policy = "NORMAL" if "NORMAL" in policies else next(iter(policies.keys()), "SAFE")

        p = dict(policies.get(policy, {}))
        return GovernanceDecision(
            policy_name=str(policy),
            max_games_mult=float(p.get("max_games_mult", 1.0)),
            pool_size_delta=int(p.get("pool_size_delta", 0)),
            coverage_alpha=float(p.get("coverage_alpha", 0.25)),
            min_pair_coverage=float(p.get("min_pair_coverage", 0.30)),
            max_clone_jaccard=float(p.get("max_clone_jaccard", 0.75)),
            actions=actions,
            reason=str(reason),
        )

    def apply_policy_to_generation(self, decision: GovernanceDecision, gen_params: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(gen_params or {})
        max_jogos = int(out.get("max_jogos", 40))
        pool_size = int(out.get("pool_size", 30))

        out["max_jogos"] = max(8, int(round(float(max_jogos) * float(decision.max_games_mult))))
        out["pool_size"] = max(16, int(pool_size + int(decision.pool_size_delta)))
        out["coverage_alpha"] = float(decision.coverage_alpha)
        out["min_pair_coverage"] = float(decision.min_pair_coverage)
        out["max_clone_jaccard"] = float(decision.max_clone_jaccard)
        return out

    def governance_actions(self, decision: GovernanceDecision, system_handles: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        anti = dict(self.cfg.get("anti_self_deception", {}))
        freeze_on_true_red = bool(anti.get("freeze_autotuning_on_true_red", anti.get("freeze_autotuning_on_red", True)))
        if freeze_on_true_red and "TRUE_RED_SAFE" in list(decision.actions):
            freeze_steps = int(anti.get("freeze_autotuning_steps", 500))
            current_step = int(self.history.get("last_eval_step", 0))
            if self.maybe_freeze(self.history, anti, current_step):
                cb = system_handles.get("freeze_autotuning") if isinstance(system_handles, dict) else None
                if callable(cb):
                    cb(int(freeze_steps))
                out.append(f"FREEZE_AUTOTUNING:{int(freeze_steps)}")
        return out


def ensure_governance_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS governance_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER,
          step INTEGER,
          created_at TEXT,
          status TEXT,
          confidence REAL,
          delta14 REAL,
          reward_avg REAL,
          trend REAL,
          policy TEXT,
          params_json TEXT,
          reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gov_run_step ON governance_decisions(run_id, step);
        """
    )


def save_governance_decision(
    conn: sqlite3.Connection,
    inputs: GovernanceInputs,
    decision: GovernanceDecision,
    applied_params: Dict[str, Any],
    created_at: str,
) -> None:
    payload = {
        "decision": asdict(decision),
        "applied_params": dict(applied_params or {}),
    }
    conn.execute(
        """
        INSERT INTO governance_decisions(
          run_id, step, created_at, status, confidence, delta14, reward_avg, trend, policy, params_json, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(inputs.run_id),
            int(inputs.step),
            str(created_at),
            str(inputs.status),
            float(0.5 if inputs.confidence_score is None else inputs.confidence_score),
            float(inputs.delta14),
            float(inputs.reward_avg),
            float(inputs.trend),
            str(decision.policy_name),
            json.dumps(payload, ensure_ascii=False),
            str(decision.reason),
        ),
    )
