import sqlite3

from training.backtest.backtest_smart_engine import (
    ArmStats,
    RecipeStats,
    SmartArm,
    SmartRecipe,
    build_per_brain_map,
    choose_arm_ucb,
    choose_recipe_ucb,
    compute_reward,
    detect_regime,
    ensure_seed_recipes,
    ensure_smart_tables,
    evolve_recipe,
    get_smart_checkpoint,
    load_recipes,
    register_hypothesis,
    revive_parked_recipes,
    set_smart_checkpoint,
    update_recipe_status,
)


def test_choose_arm_ucb_prioritizes_unpulled():
    arms = [
        SmartArm("a", 120, 100, 60, 10),
        SmartArm("b", 200, 120, 70, 20),
    ]
    stats = {"a": ArmStats(pulls=1, reward_sum=1.0), "b": ArmStats(pulls=0, reward_sum=0.0)}

    chosen = choose_arm_ucb(arms=arms, stats=stats, total_steps=10, c=1.0)
    assert chosen.name == "b"


def test_build_per_brain_map_boosts_top_scores_and_recipe_boosts():
    ids = ["x", "y", "z"]
    scores = {"x": 0.9, "y": 0.2, "z": 0.0}

    per_map = build_per_brain_map(ids, scores, base_per_brain=80, boost_top_brains=20, recipe_boosts={"y": 30})

    assert per_map["x"] > per_map["z"]
    assert per_map["y"] > per_map["z"]
    assert min(per_map.values()) >= 20


def test_checkpoint_tables_are_created_safely_and_hypothesis_table_exists():
    conn = sqlite3.connect(":memory:")
    try:
        ensure_smart_tables(conn)
        assert get_smart_checkpoint(conn) == 0
        set_smart_checkpoint(conn, 123)
        assert get_smart_checkpoint(conn) == 123

        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_smart_hypotheses'")
        assert cur.fetchone() is not None

        register_hypothesis(conn, run_id=None, kind="recipe", title="t1", payload={"ok": True})
        c = conn.execute("SELECT COUNT(*) FROM backtest_smart_hypotheses").fetchone()
        assert int(c[0]) == 1
    finally:
        conn.close()


def test_recipe_seed_and_load_and_ucb_choice():
    conn = sqlite3.connect(":memory:")
    try:
        ensure_smart_tables(conn)
        recipes = ensure_seed_recipes(conn, [f"b{i}" for i in range(1, 13)])
        loaded = load_recipes(conn, [f"b{i}" for i in range(1, 13)])
        assert recipes
        assert loaded

        stats = {name: RecipeStats() for name in loaded}
        chosen = choose_recipe_ucb(loaded, stats, total_steps=1, c=1.0)
        assert chosen.name in loaded
    finally:
        conn.close()


def test_evolve_recipe_status_transition_and_revive():
    recipes = {
        "r1": SmartRecipe("r1", members=[f"b{i}" for i in range(1, 12)], status="promoted"),
        "r2": SmartRecipe("r2", members=[f"b{i}" for i in range(5, 16)], status="parked"),
    }
    stats = {
        "r1": RecipeStats(pulls=12, reward_sum=50.0, q15_sum=5),
        "r2": RecipeStats(pulls=10, reward_sum=20.0, q15_sum=2),
    }
    phase = {f"b{i}": float(20 - i) / 20.0 for i in range(1, 20)}

    child = evolve_recipe(recipes, stats, [f"b{i}" for i in range(1, 20)], phase, step=30, max_members=18)
    assert child.name.startswith("auto_recipe_")
    assert 8 <= len(child.members) <= 18

    weak = SmartRecipe("weak", members=["b1", "b2"])
    weak2 = update_recipe_status(weak, RecipeStats(pulls=10, reward_sum=1.0), min_pulls=8, promote_reward=2.5)
    assert weak2.status == "parked"

    revived = revive_parked_recipes(recipes, stats, phase, limit=1)
    assert revived
    assert recipes[revived[0]].status == "candidate"


def test_detect_regime_and_compute_reward():
    context = {
        "historico_recente": [
            [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
            [1,2,3,4,5,6,7,8,9,10,11,12,16,17,18],
            [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],
            [1,2,3,4,5,6,7,8,9,10,11,12,16,17,18],
        ]
    }
    regime = detect_regime(context)
    assert regime in {"estavel", "volatil", "aquecido", "frio", "neutro"}

    r = compute_reward(q14=2, q15=1, best=15, regime="estavel", repeat_rate=0.6, reward_q15=5.0, reward_q14=1.5)
    assert r > 0
