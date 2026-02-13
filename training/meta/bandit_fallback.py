from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class ContextualThompsonBandit:
    alpha: Dict[str, float] = field(default_factory=dict)
    beta: Dict[str, float] = field(default_factory=dict)

    def _k(self, context_key: str, action: str) -> str:
        return f"{context_key}|{action}"

    def _params(self, key: str) -> Tuple[float, float]:
        return self.alpha.get(key, 1.0), self.beta.get(key, 1.0)

    def choose(self, context_key: str, actions: List[str]) -> str:
        if not actions:
            return ""
        best = actions[0]
        best_sample = -1.0
        for action in actions:
            key = self._k(context_key, action)
            a, b = self._params(key)
            sample = random.betavariate(a, b)
            if sample > best_sample:
                best_sample = sample
                best = action
        return best

    def update(self, context_key: str, action: str, reward: float) -> None:
        key = self._k(context_key, action)
        a, b = self._params(key)
        success = 1.0 if float(reward) > 0.0 else 0.0
        self.alpha[key] = a + success
        self.beta[key] = b + (1.0 - success)

    def to_state(self) -> dict:
        return {"alpha": self.alpha, "beta": self.beta}

    @classmethod
    def from_state(cls, state: dict | None) -> "ContextualThompsonBandit":
        if not state:
            return cls()
        return cls(alpha=dict(state.get("alpha", {})), beta=dict(state.get("beta", {})))
