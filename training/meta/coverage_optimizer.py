from __future__ import annotations

from typing import Dict, List, Set, Tuple


class CoverageOptimizer:
    def __init__(self, cfg: dict | None = None):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.alpha = float(self.cfg.get("alpha", 0.25))
        self.min_pair_coverage = float(self.cfg.get("min_pair_coverage", 0.30))
        self.stagnation_alpha = float(self.cfg.get("stagnation_alpha", 0.40))

    @staticmethod
    def _pairs(game: List[int]) -> Set[Tuple[int, int]]:
        g = sorted(set(int(x) for x in game if x is not None))
        pairs: Set[Tuple[int, int]] = set()
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                pairs.add((g[i], g[j]))
        return pairs

    def optimize(
        self,
        candidates: List[Dict],
        max_games: int,
        alpha: float | None = None,
    ) -> List[List[int]]:
        if not candidates:
            return []
        if not self.enabled:
            ordered = sorted(candidates, key=lambda c: float(c.get("score", 0.0)), reverse=True)
            return [list(c.get("dezenas", [])) for c in ordered[: int(max_games)]]

        chosen: List[Dict] = []
        covered_pairs: Set[Tuple[int, int]] = set()
        remain = [c for c in candidates if c.get("dezenas")]
        weight = float(self.alpha if alpha is None else alpha)

        while remain and len(chosen) < int(max_games):
            best_idx = -1
            best_value = -10**9
            for i, cand in enumerate(remain):
                pairs = self._pairs(list(cand.get("dezenas", [])))
                gain = len(pairs - covered_pairs)
                score = float(cand.get("score", 0.0)) + weight * float(gain)
                if score > best_value:
                    best_value = score
                    best_idx = i
            if best_idx < 0:
                break
            selected = remain.pop(best_idx)
            chosen.append(selected)
            covered_pairs |= self._pairs(list(selected.get("dezenas", [])))

        if len(chosen) < int(max_games):
            ordered = sorted(remain, key=lambda c: float(c.get("score", 0.0)), reverse=True)
            for cand in ordered:
                chosen.append(cand)
                if len(chosen) >= int(max_games):
                    break

        return [list(c.get("dezenas", [])) for c in chosen[: int(max_games)]]
