from __future__ import annotations

import json
import random
from pathlib import Path


class ABTestingManager:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.stats = {}
        self.log_file = Path("logs/ab_testing_fallback.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def choose_slots(
        self,
        mode: str,
        available_arms: list[str] | None = None,
        available_recipes: list[str] | None = None,
        available_brains: list[str] | None = None,
        core_brains: list[str] | None = None,
    ) -> dict:
        if not self.enabled:
            return {"candidate_arms": [], "candidate_recipes": [], "candidate_brains": []}

        n_slots = int(self.cfg.get("research_slots", 4) if mode == "research" else self.cfg.get("production_slots", 1))
        core = set(core_brains or [])
        arms = random.sample(available_arms or [], k=min(n_slots, len(available_arms or [])))
        recipes = random.sample(available_recipes or [], k=min(n_slots, len(available_recipes or [])))
        exp_brains_pool = [b for b in (available_brains or []) if b not in core]
        brains = random.sample(exp_brains_pool, k=min(n_slots, len(exp_brains_pool)))
        return {"candidate_arms": arms, "candidate_recipes": recipes, "candidate_brains": brains}

    def update_result(self, key: str, reward: float, hit_max: int) -> None:
        s = self.stats.setdefault(key, {"n": 0, "reward_sum": 0.0, "hit_max": 0})
        s["n"] += 1
        s["reward_sum"] += float(reward)
        s["hit_max"] = max(s["hit_max"], int(hit_max))

    def record_experiment(self, payload: dict) -> None:
        try:
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass


    def get_state(self) -> dict:
        return {"stats": self.stats}

    def set_state(self, state: dict) -> None:
        self.stats = dict(state.get("stats", {}))
