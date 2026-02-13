import json
import sqlite3

from training.backtest.backtest_smart_engine import ensure_meta_tables
from training.meta.context_features import extract_context_features
from training.meta.meta_controller import MetaController
from training.meta.model_store import ModelStore


def _build_concursos(conn: sqlite3.Connection, n: int = 360):
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
    for c in range(1, n + 1):
        base = ((c - 1) % 25) + 1
        dezenas = [((base + i - 1) % 25) + 1 for i in range(15)]
        conn.execute(
            "INSERT INTO concursos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c, *dezenas),
        )
    conn.commit()


def test_meta_pipeline_logs_and_checkpoint(tmp_path):
    conn = sqlite3.connect(":memory:")
    try:
        _build_concursos(conn)
        ensure_meta_tables(conn)

        cfg = {
            "enabled": True,
            "confidence_threshold": 0.95,
            "hidden_units": 32,
            "learning_rate": 0.001,
            "batch_size": 32,
            "train_every_steps": 5,
            "fallback_enabled": True,
        }
        store = ModelStore(tmp_path / "meta_controller.pkl")
        meta = MetaController(cfg, model_store=store)

        run_id = 1
        conn.execute(
            "INSERT INTO runs(id, started_at, mode, config_hash, seed, status) VALUES (1,'2024-01-01 00:00:00','test','abc',123,'running')"
        )

        arms = ["smart_conservador", "smart_balanceado", "smart_agressivo"]
        recipes = ["seed_all", "seed_conservador", "seed_agressivo"]
        fallback_count = 0

        for step in range(1, 21):
            concurso_ref = 200 + step
            features = extract_context_features(conn, concurso_ref)
            decision = meta.decide(features, arms, recipes, arms[0], recipes[0], regime_unstable=(step % 7 == 0))
            fallback_count += int(decision["fallback_used"])

            conn.execute(
                "INSERT INTO context_snapshots(run_id, step, concurso_ref, features_json, created_at) VALUES (?,?,?,?,?)",
                (run_id, step, concurso_ref, json.dumps(features), "2024-01-01 00:00:00"),
            )
            conn.execute(
                "INSERT INTO decisions(run_id, step, arm, recipe, exploration_rate, confidence, fallback_used, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    step,
                    decision["arm"],
                    decision["recipe"],
                    decision["exploration_rate"],
                    decision["confidence"],
                    decision["fallback_used"],
                    "2024-01-01 00:00:00",
                ),
            )

            reward = 1.0 if step % 3 == 0 else -0.2
            hit_max = 14 if reward > 0 else 13
            conn.execute(
                "INSERT INTO outcomes(run_id, step, concurso_ref, hit_max, reward, diversity, created_at) VALUES (?,?,?,?,?,?,?)",
                (run_id, step, concurso_ref + 1, hit_max, reward, 0.55, "2024-01-01 00:00:00"),
            )
            conn.commit()
            meta.train_step(features, decision, reward, regime_unstable=(step % 7 == 0))

        ctx_count = conn.execute("SELECT COUNT(*) FROM context_snapshots").fetchone()[0]
        dec_count = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        out_count = conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]

        assert int(ctx_count) == 20
        assert int(dec_count) == 20
        assert int(out_count) == 20
        assert fallback_count >= 1
        assert store.path.exists()
    finally:
        conn.close()
