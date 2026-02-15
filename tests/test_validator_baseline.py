import sqlite3
import time

from training.meta.promotion import PromotionManager
from training.validation.baseline_models import BaselineGenerator
from training.validation.metrics import compute_hits_distribution, compute_portfolio_diversity, compute_score_summary
from training.validation.validator import StrategyValidator


def _mk_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE concursos (
            concurso INTEGER PRIMARY KEY,
            d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
            d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
            d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER
        )
        """
    )
    for c in range(1, 401):
        base = (c % 25) + 1
        dezenas = [((base + i - 1) % 25) + 1 for i in range(15)]
        conn.execute("INSERT INTO concursos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (c, *dezenas))
    conn.commit()


def test_validator_baseline_and_promotion_gate():
    conn = sqlite3.connect(":memory:")
    try:
        _mk_db(conn)
        bcfg = {"enabled": True, "variants": ["global", "recent_120"], "max_games": 40}
        vcfg = {
            "enabled": True,
            "train_window": 120,
            "valid_window": 120,
            "gap": 0,
            "sample_concursos": 5,
            "promote_margin_score": 0.01,
            "promote_margin_hit": 0.0,
            "require_both_baselines": False,
        }
        validator = StrategyValidator(conn, vcfg, bcfg)

        baseline = BaselineGenerator(conn, bcfg)
        g = baseline.generate(300, 15, 30, "global")
        assert g

        res = [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]
        hs = compute_hits_distribution(g, res)
        sm = compute_score_summary(hs, compute_portfolio_diversity(g))
        assert "score_proxy" in sm

        def candidate_callable(concurso_ref: int, tipo_jogo: int, max_games: int, context: dict):
            return baseline.generate(concurso_ref, tipo_jogo, max_games, "recent_120")

        report = validator.validate_candidate(candidate_callable, 320, 15, 30, {"x": 1})
        assert "passes_baseline" in report
        assert "passes_validation" in report

        pm = PromotionManager({"promote_margin_reward": 0.1, "promote_margin_score": 0.01})
        decision = pm.evaluate_candidate({"n": 20, **report}, {"mean_reward": 0.0, "hit_max": 13})
        if report["passes_baseline"] and report["passes_validation"]:
            assert decision in {"promote", "keep_testing"}
        else:
            assert decision in {"park", "keep_testing"}
    finally:
        conn.close()


def test_validator_timeout_degrade_limits_validated_count():
    conn = sqlite3.connect(":memory:")
    try:
        _mk_db(conn)
        bcfg = {"enabled": True, "variants": ["global", "recent_120"], "max_games": 20}
        vcfg = {
            "enabled": True,
            "train_window": 120,
            "valid_window": 120,
            "gap": 0,
            "sample_concursos": 20,
            "validate_soft_timeout_s": 0.1,
            "validate_degrade_ref_fraction": 0.25,
            "validate_min_refs_after_timeout": 4,
        }
        validator = StrategyValidator(conn, vcfg, bcfg)

        def slow_candidate(concurso_ref: int, tipo_jogo: int, max_games: int, context: dict):
            time.sleep(0.05)
            return [list(range(1, 16)) for _ in range(min(5, max_games))]

        report = validator.validate_candidate(slow_candidate, 320, 15, 30, {})
        assert report.get("degraded") is True
        assert report.get("timeout_action") == "degrade_max_games_and_limit_refs"
        assert int(report.get("validated_count", 0)) <= 8
    finally:
        conn.close()


def test_validator_short_circuit_invalid_candidate_games():
    conn = sqlite3.connect(":memory:")
    try:
        _mk_db(conn)
        bcfg = {"enabled": True, "variants": ["global", "recent_120"], "max_games": 20}
        vcfg = {
            "enabled": True,
            "train_window": 120,
            "valid_window": 120,
            "gap": 0,
            "sample_concursos": 8,
            "validate_soft_timeout_s": 2.0,
        }
        validator = StrategyValidator(conn, vcfg, bcfg)

        def invalid_candidate(concurso_ref: int, tipo_jogo: int, max_games: int, context: dict):
            return [[1, 1, 2], [30] * 15]

        report = validator.validate_candidate(invalid_candidate, 320, 15, 30, {})
        assert "passes_validation" in report
        assert report["candidate_hit_max_mean"] == 0.0
    finally:
        conn.close()
