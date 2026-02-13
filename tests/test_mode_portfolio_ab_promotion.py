from training.meta.ab_testing import ABTestingManager
from training.meta.mode_manager import ModeManager
from training.meta.portfolio_builder import PortfolioBuilder
from training.meta.promotion import PromotionManager
from training.meta.regime_detector import REGIME_ESTAVEL, REGIME_INSTAVEL
from training.meta.diversity import portfolio_diversity


def test_mode_portfolio_ab_and_promotion_sanity_60_steps():
    mode_cfg = {
        "enabled": True,
        "cooldown_steps": 5,
        "switch_to_research": {"on_instable_regime": True, "on_rescue_mode": True, "bad_perf_steps": 8},
        "switch_to_production": {"stable_steps": 10},
        "core_brains": ["b1", "b2"],
    }
    portfolio_cfg = {
        "enabled": True,
        "production": {"quota_even": [7, 8, 9], "quota_sum_ranges": [[170, 195], [196, 215], [216, 235]], "max_clone_jaccard": 0.7},
        "research": {"quota_even": [6, 7, 8, 9, 10], "quota_sum_ranges": [[165, 190], [191, 210], [211, 240]], "max_clone_jaccard": 0.78},
    }
    ab_cfg = {"enabled": True, "production_slots": 1, "research_slots": 4, "test_window_steps": 50, "promote_margin_reward": 0.1}

    mm = ModeManager(mode_cfg)
    pb = PortfolioBuilder(portfolio_cfg)
    ab = ABTestingManager(ab_cfg)
    pm = PromotionManager(ab_cfg)

    modes = []
    all_slots = []

    for step in range(1, 61):
        regime = REGIME_INSTAVEL if step in {8, 9, 10, 30} else REGIME_ESTAVEL
        stagnation = {"rescue_mode": step in {31, 32}}
        recent_perf = {"step": step, "is_bad": 12 <= step <= 22, "is_stable": step >= 40}
        mode = mm.decide_mode(regime, stagnation, recent_perf)
        modes.append(mode)

        slots = ab.choose_slots(
            mode=mode,
            available_arms=["a1", "a2", "a3", "a4"],
            available_recipes=["r1", "r2", "r3", "r4"],
            available_brains=["b1", "b2", "b3", "b4", "b5"],
            core_brains=mode_cfg["core_brains"],
        )
        all_slots.append(slots)

        cands = []
        for i in range(30):
            dezenas = sorted({((i + j + step) % 25) + 1 for j in range(15)})
            if len(dezenas) < 15:
                dezenas = list(range(1, 16))
            cands.append(
                {
                    "dezenas": dezenas,
                    "score": 100 - i,
                    "origem": "x",
                    "features": {"even": sum(1 for d in dezenas if d % 2 == 0), "sum": sum(dezenas), "repeated": 0},
                }
            )
        portfolio = pb.build(cands, max_games=15, mode=mode, quotas={})
        div = portfolio_diversity(portfolio)
        assert 0.0 <= div <= 1.0

    assert "research" in modes
    assert modes[-1] == "production"

    assert any(len(s["candidate_brains"]) >= 1 for s in all_slots)

    # core brains are excluded from experimental slots in production
    for mode, slots in zip(modes, all_slots):
        if mode == "production":
            assert all(b not in mode_cfg["core_brains"] for b in slots["candidate_brains"])

    decision = pm.evaluate_candidate(
        {"n": 30, "mean_reward": 0.5, "hit_max": 14},
        {"mean_reward": 0.2, "hit_max": 13},
    )
    assert decision == "promote"
