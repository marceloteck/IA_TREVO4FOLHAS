from training.meta.governance import GovernanceInputs, GovernanceManager


def _inputs(conf: float, step: int, ent: float = 0.7, clone: float = 0.3):
    return GovernanceInputs(
        status="stable",
        confidence_score=conf,
        delta14=0.0,
        reward_avg=0.0,
        trend=0.0,
        structural_stagnation=False,
        clone_ratio=clone,
        entropy=ent,
        pair_coverage=0.3,
        step=step,
        run_id=1,
    )


def test_governance_hysteresis_enter_and_exit_safe():
    cfg = {
        "enabled": True,
        "decision_rules": {"gov_low_enter": 0.45, "gov_low_exit": 0.50, "conf_ema_alpha": 1.0},
        "policies": {"NORMAL": {}, "SAFE": {}, "AGGRESSIVE": {}},
    }
    gov = GovernanceManager(cfg)

    d1 = gov.choose_policy(_inputs(0.44, 1))
    assert d1.policy_name == "SAFE"

    d2 = gov.choose_policy(_inputs(0.47, 2))
    assert d2.policy_name == "SAFE"

    d3 = gov.choose_policy(_inputs(0.52, 3))
    assert d3.policy_name in {"NORMAL", "AGGRESSIVE"}


def test_governance_diversity_override_allows_normal_from_safe():
    cfg = {
        "enabled": True,
        "decision_rules": {
            "gov_low_enter": 0.45,
            "gov_low_exit": 0.50,
            "conf_ema_alpha": 1.0,
            "safe_diversity_entropy_min": 0.60,
            "safe_diversity_clone_max": 0.35,
            "safe_diversity_cov_min": 0.20,
            "safe_diversity_conf_margin": 0.02,
        },
        "policies": {"NORMAL": {}, "SAFE": {}, "AGGRESSIVE": {}},
    }
    gov = GovernanceManager(cfg)
    gov.choose_policy(_inputs(0.43, 1, ent=0.8, clone=0.2))
    d = gov.choose_policy(_inputs(0.49, 2, ent=0.8, clone=0.2))

    assert d.policy_name == "NORMAL"
    assert "DIVERSITY_OVERRIDE" in d.actions
