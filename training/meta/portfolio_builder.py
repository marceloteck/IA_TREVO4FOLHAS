from __future__ import annotations

from collections import defaultdict

from training.meta.diversity import jaccard


class PortfolioBuilder:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))

    def _mode_cfg(self, mode: str) -> dict:
        return self.cfg.get(mode, self.cfg.get("production", {}))

    def build(self, candidates: list[dict], max_games: int, mode: str, quotas: dict) -> list[list[int]]:
        if not self.enabled:
            return [c["dezenas"] for c in sorted(candidates, key=lambda x: float(x.get("score", 0.0)), reverse=True)[: int(max_games)]]

        mode_cfg = self._mode_cfg(mode)
        max_clone = float((quotas or {}).get("max_clone_jaccard_override", mode_cfg.get("max_clone_jaccard", 0.70)))
        quota_even = set(int(x) for x in mode_cfg.get("quota_even", []))
        sum_ranges = [tuple(r) for r in mode_cfg.get("quota_sum_ranges", [])]

        ordered = sorted(candidates, key=lambda x: float(x.get("score", 0.0)), reverse=True)
        selected: list[dict] = []
        even_count = defaultdict(int)
        sum_count = defaultdict(int)

        target_even_each = max(1, int(max_games / max(1, len(quota_even)))) if quota_even else 0
        target_sum_each = max(1, int(max_games / max(1, len(sum_ranges)))) if sum_ranges else 0

        for cand in ordered:
            dezenas = list(cand.get("dezenas", []))
            if not dezenas:
                continue
            sset = set(dezenas)

            if any(jaccard(sset, set(s["dezenas"])) > max_clone for s in selected):
                continue

            even = int(cand.get("features", {}).get("even", sum(1 for d in dezenas if int(d) % 2 == 0)))
            ssum = int(cand.get("features", {}).get("sum", sum(int(d) for d in dezenas)))

            even_ok = True
            if quota_even:
                even_ok = (even in quota_even) and (even_count[even] < target_even_each or len(selected) >= int(max_games * 0.6))

            sum_bucket = None
            if sum_ranges:
                for lo, hi in sum_ranges:
                    if lo <= ssum <= hi:
                        sum_bucket = (lo, hi)
                        break
                if sum_bucket is not None and sum_count[sum_bucket] >= target_sum_each and len(selected) < int(max_games * 0.7):
                    even_ok = False

            if not even_ok:
                continue

            selected.append(cand)
            even_count[even] += 1
            if sum_bucket is not None:
                sum_count[sum_bucket] += 1

            if len(selected) >= int(max_games):
                break

        if len(selected) < int(max_games):
            used = {tuple(x["dezenas"]) for x in selected}
            for cand in ordered:
                key = tuple(cand.get("dezenas", []))
                if key in used:
                    continue
                selected.append(cand)
                used.add(key)
                if len(selected) >= int(max_games):
                    break

        final_selected = selected[: int(max_games)]
        # Camada superior opcional: coverage optimizer (fallback total para fluxo antigo)
        cov_opt = None
        try:
            cov_opt = (quotas or {}).get("coverage_optimizer")
        except Exception:
            cov_opt = None
        if cov_opt is not None:
            try:
                alpha_boost = float((quotas or {}).get("coverage_alpha_boost", 0.0))
                is_stag = bool((quotas or {}).get("structural_stagnation", False))
                base_alpha = float(getattr(cov_opt, "alpha", 0.25))
                stag_alpha = float(getattr(cov_opt, "stagnation_alpha", 0.40))
                alpha = max(base_alpha, stag_alpha) if is_stag else base_alpha
                alpha += alpha_boost
                optimized = cov_opt.optimize(final_selected, int(max_games), alpha=alpha)
                if optimized:
                    return [list(g) for g in optimized[: int(max_games)]]
            except Exception:
                pass

        return [list(x["dezenas"]) for x in final_selected]
