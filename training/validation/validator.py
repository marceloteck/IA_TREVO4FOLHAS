from __future__ import annotations

import json
import random
import sqlite3
import time
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


    @staticmethod
    def _is_valid_game(game: list[int], tipo_jogo: int) -> bool:
        if not isinstance(game, (list, tuple)):
            return False
        if len(game) != int(tipo_jogo):
            return False
        try:
            nums = [int(x) for x in game]
        except Exception:
            return False
        if any(n < 1 or n > 25 for n in nums):
            return False
        return len(set(nums)) == len(nums)

    @staticmethod
    def _portfolio_signature(games: list[list[int]]) -> tuple[tuple[int, ...], ...]:
        out = []
        for g in games or []:
            try:
                out.append(tuple(sorted(int(x) for x in g)))
            except Exception:
                continue
        return tuple(sorted(out))

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

        heartbeat_cb = context.get("heartbeat") if isinstance(context, dict) else None
        heartbeat_every = max(1, int(self.cfg.get("validate_heartbeat_every", 50)))
        heartbeat_seconds = max(0.2, float(self.cfg.get("validate_heartbeat_seconds", 2.0)))
        soft_timeout_s = max(0.1, float(self.cfg.get("validate_soft_timeout_s", 20.0)))
        degrade_fraction = min(1.0, max(0.1, float(self.cfg.get("validate_degrade_fraction", 0.5))))
        validate_min_candidates = max(1, int(self.cfg.get("validate_min_candidates", 50)))
        degrade_ref_fraction = min(1.0, max(0.1, float(self.cfg.get("validate_degrade_ref_fraction", 0.6))))
        min_refs_after_timeout = max(3, int(self.cfg.get("validate_min_refs_after_timeout", 6)))
        progress_log_s = max(1.0, float(self.cfg.get("validate_progress_log_s", 5.0)))

        t0 = time.perf_counter()
        last_heartbeat_ts = t0
        last_progress_ts = t0
        last_ok = 0
        last_fail = 0
        degraded = False
        timeout_action = "none"
        degraded_max_games = max(1, int(max_games))
        max_refs_after_timeout = max(min_refs_after_timeout, int(round(len(refs) * degrade_ref_fraction)))
        summary_cache: dict[tuple[tuple[int, ...], tuple[tuple[int, ...], ...], bool], dict] = {}
        basic_valid_cache: dict[tuple[int, ...], bool] = {}
        cache_hits = 0
        cache_miss = 0

        for idx, ref in enumerate(refs, start=1):
            now = time.perf_counter()
            elapsed = now - t0
            elapsed_since_hb = now - last_heartbeat_ts
            should_hb = idx == 1 or (idx % heartbeat_every == 0) or (elapsed_since_hb >= heartbeat_seconds)
            if callable(heartbeat_cb) and should_hb:
                done = max(1, last_ok + last_fail)
                payload = {
                    "phase": "generate_candidates",
                    "subphase": "validate_candidate",
                    "elapsed": elapsed,
                    "rate": float(done) / max(1e-9, elapsed),
                    "last_ok": int(last_ok),
                    "last_fail": int(last_fail),
                }
                if len(refs) > 1:
                    payload["i"] = idx
                    payload["n"] = len(refs)
                heartbeat_cb(payload)
                last_heartbeat_ts = now

            if not degraded and elapsed >= soft_timeout_s:
                degraded = True
                degraded_max_games = max(validate_min_candidates, int(round(float(max_games) * degrade_fraction)))
                timeout_action = "degrade_max_games_and_limit_refs"
                print(
                    f"⚠️ validate_candidate timeout_action={timeout_action} elapsed={elapsed:.1f}s max_games={int(max_games)}->{int(degraded_max_games)} max_refs={max_refs_after_timeout}/{len(refs)}",
                    flush=True,
                )

            validated_count = last_ok + last_fail
            if degraded and validated_count >= max_refs_after_timeout:
                break

            result = self._result_for(ref)
            if not result:
                last_fail += 1
                continue

            current_max_games = degraded_max_games if degraded else int(max_games)
            cand_games = candidate_callable(ref, int(tipo_jogo), int(current_max_games), context) or []

            cand_games = [list(g) for g in cand_games if isinstance(g, (list, tuple))]
            invalid_candidate = False
            valid_cand_games = []
            for g in cand_games:
                sig = tuple(sorted(int(x) for x in g)) if all(isinstance(x, (int, float)) for x in g) else tuple()
                if sig in basic_valid_cache:
                    ok = basic_valid_cache[sig]
                else:
                    ok = self._is_valid_game(g, int(tipo_jogo))
                    basic_valid_cache[sig] = ok
                if ok:
                    valid_cand_games.append(g)
                else:
                    invalid_candidate = True

            def _compute_summary(games: list[list[int]], include_diversity: bool) -> dict:
                nonlocal cache_hits, cache_miss
                key = (tuple(result), self._portfolio_signature(games), bool(include_diversity))
                if key in summary_cache:
                    cache_hits += 1
                    return summary_cache[key]
                cache_miss += 1
                if include_diversity:
                    out = compute_score_summary(compute_hits_distribution(games, result), compute_portfolio_diversity(games))
                else:
                    out = compute_score_summary(compute_hits_distribution(games, result), diversity=0.0)
                summary_cache[key] = out
                return out

            g_games = self.baseline.generate(ref, int(tipo_jogo), int(current_max_games), variant="global")
            r_games = self.baseline.generate(ref, int(tipo_jogo), int(current_max_games), variant="recent_120")

            include_diversity = not degraded
            if invalid_candidate and not valid_cand_games:
                cand_sum = {"score_proxy": 0.0, "hit_max": 0.0}
            else:
                cand_sum = _compute_summary(valid_cand_games, include_diversity)
            g_sum = _compute_summary(g_games, include_diversity)
            r_sum = _compute_summary(r_games, include_diversity)

            cand_scores.append(float(cand_sum["score_proxy"]))
            bglob_scores.append(float(g_sum["score_proxy"]))
            brec_scores.append(float(r_sum["score_proxy"]))
            cand_hit.append(float(cand_sum["hit_max"]))
            base_hit.append(max(float(g_sum["hit_max"]), float(r_sum["hit_max"])))
            last_ok += 1

            now2 = time.perf_counter()
            if (now2 - last_progress_ts) >= progress_log_s:
                eval_count = max(1, last_ok + last_fail)
                avg_ms = ((now2 - t0) * 1000.0) / float(eval_count)
                hit_rate = float(cache_hits) / max(1.0, float(cache_hits + cache_miss))
                print(
                    f"ℹ️ validate_candidate progress validated={eval_count}/{len(refs)} rate={eval_count/max(1e-9,now2-t0):.2f}/s cache_hit_rate={hit_rate:.2%} avg_eval_ms={avg_ms:.1f}",
                    flush=True,
                )
                last_progress_ts = now2

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
            "degraded": bool(degraded),
            "validated_count": int(last_ok + last_fail),
            "timeout_action": str(timeout_action),
            "reason": "ok" if passes_validation else "below_baseline_or_low_margin",
        }

        with (self.log_dir / "validator_reports.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
        return report
