from __future__ import annotations

from collections import deque


class StagnationTracker:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.window_steps = max(5, int(self.cfg.get("window_steps", 40)))
        self.stagnation_steps_max = max(10, int(self.cfg.get("stagnation_steps_max", 80)))
        self.threshold = float(self.cfg.get("threshold", 0.60))

        self.best_hit = -1
        self.recent_rewards = deque(maxlen=self.window_steps)
        self.stagnation_steps = 0
        self.rescue_mode = False
        self.rescue_since = 0

    def update(self, hit_max: int, reward: float, arm: str, recipe: str) -> dict:
        if not self.enabled:
            return {"stagnation_score": 0.0, "stagnation_steps": 0, "rescue_mode": False}

        prev_avg = sum(self.recent_rewards) / float(len(self.recent_rewards)) if self.recent_rewards else float(reward)
        self.recent_rewards.append(float(reward))

        improved = int(hit_max) > self.best_hit
        if improved:
            self.best_hit = int(hit_max)
            self.stagnation_steps = max(0, self.stagnation_steps - 2)
        else:
            if float(reward) < float(prev_avg):
                self.stagnation_steps += 1
            else:
                self.stagnation_steps += 0

        score = min(1.0, self.stagnation_steps / float(self.stagnation_steps_max))
        self.rescue_mode = score >= self.threshold
        if self.rescue_mode:
            self.rescue_since += 1
        else:
            self.rescue_since = 0

        return {
            "stagnation_score": float(score),
            "stagnation_steps": int(self.stagnation_steps),
            "rescue_mode": bool(self.rescue_mode),
            "arm": str(arm),
            "recipe": str(recipe),
            "rescue_since": int(self.rescue_since),
        }

    def peek(self) -> dict:
        score = min(1.0, self.stagnation_steps / float(self.stagnation_steps_max)) if self.enabled else 0.0
        return {
            "stagnation_score": float(score),
            "stagnation_steps": int(self.stagnation_steps),
            "rescue_mode": bool(self.rescue_mode),
            "rescue_since": int(self.rescue_since),
        }


    def get_state(self) -> dict:
        return {
            "best_hit": int(self.best_hit),
            "stagnation_steps": int(self.stagnation_steps),
            "rescue_mode": bool(self.rescue_mode),
            "rescue_since": int(self.rescue_since),
            "recent_rewards": list(self.recent_rewards),
        }

    def set_state(self, state: dict) -> None:
        self.best_hit = int(state.get("best_hit", self.best_hit))
        self.stagnation_steps = int(state.get("stagnation_steps", self.stagnation_steps))
        self.rescue_mode = bool(state.get("rescue_mode", self.rescue_mode))
        self.rescue_since = int(state.get("rescue_since", self.rescue_since))
        rr = list(state.get("recent_rewards", []))[-self.window_steps :]
        self.recent_rewards.clear()
        self.recent_rewards.extend(float(x) for x in rr)
