from __future__ import annotations

import json
import random
import sqlite3
from pathlib import Path

from training.validation.baseline_models import BaselineGenerator
from training.validation.metrics import compute_hits_distribution, compute_portfolio_diversity, compute_score_summary
from training.validation.window_split import get_validation_windows


class StrategyValidator:
    def __init__(self, db_conn, cfg: dict, baseline_cfg: dict):
        self.conn: sqlite3.Connection = db_conn
        self.cfg = dict(cfg or {})
        self.baseline_cfg = dict(baseline_cfg or {})
        self.baseline = BaselineGenerator(self.conn, self.baseline_cfg)
        self.log_dir = Path("logs/validator")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _result_for(self, concurso: int) -> list[int] | None:
        row = self.conn.execute(
            "SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15 FROM concursos WHERE concurso=?",
            (int(concurso),),
        ).fetchone()
        return [int(x) for x in row] if row else None

    def _sample_refs(self, start: int, end: int, n: int) -> list[int]:
        if end < start:
            return []
        pool = list(range(int(start), int(end) + 1))
        if len(pool) <= n:
            return pool
        idxs = [int(round(i * (len(pool) - 1) / float(n - 1))) for i in range(n)]
        return sorted(set(pool[i] for i in idxs))

    def validate_candidate(self, candidate_callable, concurso_ref: int, tipo_jogo: int, max_games: int, context: dict) -> dict:
        if not bool(self.cfg.get("enabled", True)):
            return {
                "candidate_score_mean": 0.0,
                "baseline_global_mean": 0.0,
                "baseline_recent_mean": 0.0,
                "candidate_hit_max_mean": 0.0,
                "baseline_hit_max_mean": 0.0,
                "passes_baseline": True,
                "passes_validation": True,
                "reason": "validator_disabled",
            }

        windows = get_validation_windows(int(concurso_ref), self.cfg)
        vstart, vend = windows["window_valid"]
        sample_n = max(1, int(self.cfg.get("sample_concursos", 20)))
        refs = self._sample_refs(vstart, vend, sample_n)

        cand_scores = []
        bglob_scores = []
        brec_scores = []
        cand_hit = []
        base_hit = []

        for ref in refs:
            result = self._result_for(ref)
            if not result:
                continue

            cand_games = candidate_callable(ref, int(tipo_jogo), int(max_games), context) or []
            g_games = self.baseline.generate(ref, int(tipo_jogo), int(max_games), variant="global")
            r_games = self.baseline.generate(ref, int(tipo_jogo), int(max_games), variant="recent_120")

            cand_sum = compute_score_summary(compute_hits_distribution(cand_games, result), compute_portfolio_diversity(cand_games))
            g_sum = compute_score_summary(compute_hits_distribution(g_games, result), compute_portfolio_diversity(g_games))
            r_sum = compute_score_summary(compute_hits_distribution(r_games, result), compute_portfolio_diversity(r_games))

            cand_scores.append(float(cand_sum["score_proxy"]))
            bglob_scores.append(float(g_sum["score_proxy"]))
            brec_scores.append(float(r_sum["score_proxy"]))
            cand_hit.append(float(cand_sum["hit_max"]))
            base_hit.append(max(float(g_sum["hit_max"]), float(r_sum["hit_max"])))

        if not cand_scores:
            return {
                "candidate_score_mean": 0.0,
                "baseline_global_mean": 0.0,
                "baseline_recent_mean": 0.0,
                "candidate_hit_max_mean": 0.0,
                "baseline_hit_max_mean": 0.0,
                "passes_baseline": False,
                "passes_validation": False,
                "reason": "no_validation_samples",
            }

        cmean = sum(cand_scores) / len(cand_scores)
        gmean = sum(bglob_scores) / len(bglob_scores)
        rmean = sum(brec_scores) / len(brec_scores)
        chit = sum(cand_hit) / len(cand_hit)
        bhit = sum(base_hit) / len(base_hit)

        margin_score = float(self.cfg.get("promote_margin_score", 0.08))
        margin_hit = float(self.cfg.get("promote_margin_hit", 0.0))
        require_both = bool(self.cfg.get("require_both_baselines", True))

        pass_global = cmean >= gmean + margin_score and chit >= bhit + margin_hit
        pass_recent = cmean >= rmean + margin_score and chit >= bhit + margin_hit
        passes_baseline = pass_global and pass_recent if require_both else (pass_global or pass_recent)
        passes_validation = passes_baseline and len(cand_scores) >= max(3, sample_n // 4)

        report = {
            "candidate_score_mean": float(cmean),
            "baseline_global_mean": float(gmean),
            "baseline_recent_mean": float(rmean),
            "candidate_hit_max_mean": float(chit),
            "baseline_hit_max_mean": float(bhit),
            "passes_baseline": bool(passes_baseline),
            "passes_validation": bool(passes_validation),
            "reason": "ok" if passes_validation else "below_baseline_or_low_margin",
        }

        with (self.log_dir / "validator_reports.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
        return report
