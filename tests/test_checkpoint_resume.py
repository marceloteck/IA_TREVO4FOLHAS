import random
import sqlite3

import numpy as np

from training.meta.ab_testing import ABTestingManager
from training.meta.checkpoint import CheckpointManager
from training.meta.mode_manager import ModeManager
from training.meta.stagnation import StagnationTracker


def test_checkpoint_save_load_and_restore_states():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, status TEXT)")
        conn.execute("INSERT INTO runs(id, status) VALUES (1, 'running')")

        ck = CheckpointManager(conn, {"enabled": True, "max_keep_checkpoints": 5})
        mm = ModeManager({"enabled": True, "cooldown_steps": 2, "switch_to_research": {"on_instable_regime": True, "bad_perf_steps": 3}, "switch_to_production": {"stable_steps": 3}})
        st = StagnationTracker({"enabled": True, "window_steps": 10, "stagnation_steps_max": 20, "threshold": 0.5})
        ab = ABTestingManager({"enabled": True, "production_slots": 1, "research_slots": 2})

        random.seed(123)
        np.random.seed(123)
        _ = [random.random() for _ in range(3)]
        _ = np.random.rand(3)

        mode = mm.decide_mode(3, {"rescue_mode": False}, {"step": 5, "is_bad": False, "is_stable": False})
        stag = st.update(hit_max=13, reward=-0.2, arm="a", recipe="r")
        ab.update_result("k", -0.2, 13)

        state = {
            "run_id": 1,
            "step": 7,
            "concurso_ref": 120,
            "rng_seed_base": 123,
            "rng_state_py": "x",
            "rng_state_np": "y",
            "mode": mode,
            "mode_manager": mm.get_state(),
            "stagnation": st.get_state(),
            "ab_testing": ab.get_state(),
            "policy": {"arm": "a", "recipe": "r", "exploration_rate": 0.5, "brain_mask": ["b1"]},
            "last_diversity": 0.42,
            "last_hits_distribution": {"12": 1, "13": 2, "14": 0, "15": 0},
            "reward_history": [-0.2, 0.1],
        }
        ck.save(state)

        loaded = ck.load_latest_valid(1)
        assert loaded is not None
        assert int(loaded["step"]) == 7
        assert loaded["mode"] in {"production", "research"}

        mm2 = ModeManager({"enabled": True})
        st2 = StagnationTracker({"enabled": True})
        ab2 = ABTestingManager({"enabled": True})
        mm2.set_state(dict(loaded["mode_manager"]))
        st2.set_state(dict(loaded["stagnation"]))
        ab2.set_state(dict(loaded["ab_testing"]))

        assert mm2.get_state()["mode"] == loaded["mode_manager"]["mode"]
        assert st2.get_state()["stagnation_steps"] == loaded["stagnation"]["stagnation_steps"]
        assert ab2.get_state()["stats"] == loaded["ab_testing"]["stats"]
    finally:
        conn.close()


def test_checkpoint_marks_corrupted_as_invalid_and_loads_previous():
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, status TEXT)")
        conn.execute("INSERT INTO runs(id, status) VALUES (1, 'running')")
        ck = CheckpointManager(conn, {"enabled": True})

        ck.save({"run_id": 1, "step": 1, "concurso_ref": 10})
        conn.execute(
            "INSERT INTO checkpoints(run_id, step, concurso_ref, created_at, state_json, state_hash, is_valid) VALUES (?,?,?,?,?,?,?)",
            (1, 2, 11, "x", '{"bad":1}', "wrong", 1),
        )
        conn.commit()

        loaded = ck.load_latest_valid(1)
        assert loaded is not None
        assert int(loaded["step"]) == 1

        bad = conn.execute("SELECT is_valid FROM checkpoints WHERE step=2").fetchone()
        assert int(bad[0]) == 0
    finally:
        conn.close()
