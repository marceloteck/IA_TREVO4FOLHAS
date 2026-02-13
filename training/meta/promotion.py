from __future__ import annotations


class PromotionManager:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.margin = float(self.cfg.get("promote_margin_reward", 0.10))
        self.margin_score = float(self.cfg.get("promote_margin_score", 0.08))

    def evaluate_candidate(self, candidate_stats: dict, baseline_stats: dict) -> str:
        n = int(candidate_stats.get("n", 0))
        if n < 5:
            return "keep_testing"

        if "passes_baseline" in candidate_stats or "passes_validation" in candidate_stats:
            pass_base = bool(candidate_stats.get("passes_baseline", False))
            pass_val = bool(candidate_stats.get("passes_validation", False))
            score_gain = float(candidate_stats.get("candidate_score_mean", 0.0)) - max(
                float(candidate_stats.get("baseline_global_mean", 0.0)),
                float(candidate_stats.get("baseline_recent_mean", 0.0)),
            )
            if pass_base and pass_val and score_gain >= self.margin_score:
                return "promote"
            if score_gain >= self.margin_score * 0.6:
                return "keep_testing"
            return "park"

        cand_reward = float(candidate_stats.get("mean_reward", 0.0))
        base_reward = float(baseline_stats.get("mean_reward", 0.0))
        cand_hit = int(candidate_stats.get("hit_max", 0))
        base_hit = int(baseline_stats.get("hit_max", 0))

        if cand_reward >= base_reward + self.margin and cand_hit >= base_hit:
            return "promote"

        if cand_reward < base_reward - (self.margin * 1.5):
            return "park" if n < 20 else "disable"

        return "keep_testing"
