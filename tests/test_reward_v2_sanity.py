from training.meta.diversity import portfolio_diversity
from training.meta.regime_detector import detect_regime
from training.meta.reward_v2 import compute_reward_v2
from training.meta.stagnation import StagnationTracker


def test_reward_v2_diversity_regime_stagnation_sanity_30_steps():
    diversity_cfg = {
        "enabled": True,
        "pair_sample_max": 200,
        "min_diversity": 0.35,
        "target_diversity": 0.55,
        "bonus_scale": 0.25,
        "penalty_scale": 0.60,
    }
    regime_cfg = {
        "enabled": True,
        "instability": {"drift_freq_120": 0.70, "std_sum_120": 0.70, "entropy_freq_120": 0.70},
        "reward_high": 0.60,
        "reward_low": 0.35,
    }
    reward_cfg = {
        "enabled": True,
        "weights": {"hit_max": 1.0, "distribution": 0.2, "diversity": 0.35, "stagnation": 0.55, "improve_bonus": 0.15},
        "hit_scores": {"15": 3.0, "14": 1.6, "13": 0.35, "12": 0.15, "11_or_less": -0.10},
        "distribution_bonus": {"13_each": 0.02, "12_each": 0.01, "cap": 0.35},
    }
    stagnation_cfg = {"enabled": True, "window_steps": 20, "stagnation_steps_max": 30, "threshold": 0.60}

    tracker = StagnationTracker(stagnation_cfg)
    rewards = []
    regimes = []
    diversities = []
    stag_scores = []

    for step in range(30):
        games = [[(i + step + j) % 25 + 1 for j in range(15)] for i in range(6)]
        diversity = portfolio_diversity(games, pair_sample_max=50)
        diversities.append(diversity)

        f = {
            "drift_freq_120": 0.2 if step < 20 else 0.8,
            "std_sum_120": 0.3,
            "entropy_freq_120": 0.3,
            "arm_recent_reward": 0.2 if step < 10 else 0.65,
            "stagnation_score": 0.7 if 10 <= step < 18 else 0.2,
        }
        regime_id = detect_regime(f, regime_cfg)
        regimes.append(regime_id)

        hit_max = 13 if step < 15 else 14
        legacy_reward = -0.2 if step < 15 else 0.8
        stag = tracker.update(hit_max=hit_max, reward=legacy_reward, arm="a", recipe="r")
        stag_scores.append(stag["stagnation_score"])

        reward = compute_reward_v2(
            hit_max=hit_max,
            hits_distribution={"12": 2, "13": 1 if step < 15 else 3, "14": 0 if step < 15 else 1, "15": 0},
            diversity=diversity,
            context={"legacy_reward": legacy_reward, "recent_reward_baseline": sum(rewards[-10:]) / max(1, len(rewards[-10:])), "diversity_cfg": diversity_cfg},
            decision={"arm": "a", "recipe": "r"},
            stagnation=stag,
            cfg=reward_cfg,
        )
        rewards.append(reward)

    assert all(0.0 <= d <= 1.0 for d in diversities)
    assert all(r in {0, 1, 2, 3} for r in regimes)
    assert len(set(round(x, 4) for x in rewards)) > 1
    assert max(stag_scores) >= 0.2
