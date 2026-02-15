import sqlite3

from training.meta.meta_controller import MetaController
from training.monitoring.baseline import compute_baseline_from_db


def _build_fake_db(n=120):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE concursos(
          concurso INTEGER PRIMARY KEY,
          d1 INTEGER,d2 INTEGER,d3 INTEGER,d4 INTEGER,d5 INTEGER,
          d6 INTEGER,d7 INTEGER,d8 INTEGER,d9 INTEGER,d10 INTEGER,
          d11 INTEGER,d12 INTEGER,d13 INTEGER,d14 INTEGER,d15 INTEGER
        )
        """
    )
    for i in range(1, n + 1):
        base = ((i - 1) % 11) + 1
        nums = [((base + j - 1) % 25) + 1 for j in range(15)]
        conn.execute(
            "INSERT INTO concursos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, *nums),
        )
    conn.commit()
    return conn


def test_baseline_db_proxy_not_empty_with_enough_data():
    conn = _build_fake_db(220)
    baseline = compute_baseline_from_db(conn, n_min=60, n_max=200, window=30)
    assert baseline["num_outcomes"] > 0
    assert 0.0 <= float(baseline["frequencia_recente_q14_rate"]) <= 1.0
    assert 0.0 <= float(baseline["copiar_ultimo_q14_rate"]) <= 1.0


def test_meta_controller_batch_clamp_runtime():
    mc = MetaController(config={"batch_size": 32, "train_every_steps": 1}, model_store=None)
    mc._apply_effective_batch_size(sample_count=5)
    assert int(mc.arm_model.batch_size) == 5
    assert int(mc.recipe_model.batch_size) == 5
    assert int(mc.explore_model.batch_size) == 5
