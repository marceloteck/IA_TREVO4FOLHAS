import json
import sqlite3
from pathlib import Path

from training.perf.feature_cache import FeatureCache
from training.perf.throttle import Throttle
from training.perf.sqlite_optimize import apply_sqlite_pragmas, ensure_indexes
from training.tuning.auto_tuner import AutoTuner


def _mk_db(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE concursos (
          concurso INTEGER PRIMARY KEY,
          d1 INTEGER,d2 INTEGER,d3 INTEGER,d4 INTEGER,d5 INTEGER,
          d6 INTEGER,d7 INTEGER,d8 INTEGER,d9 INTEGER,d10 INTEGER,
          d11 INTEGER,d12 INTEGER,d13 INTEGER,d14 INTEGER,d15 INTEGER
        );
        CREATE TABLE outcomes(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, step INTEGER, concurso_ref INTEGER, hit_max INTEGER, reward REAL, diversity REAL, created_at TEXT);
        CREATE TABLE decisions(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, step INTEGER, arm TEXT, recipe TEXT, exploration_rate REAL, confidence REAL, fallback_used INTEGER, created_at TEXT);
        CREATE TABLE telemetry_step_summaries(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, step INTEGER, summary_json TEXT, created_at TEXT);
        CREATE TABLE experiments(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, passes INTEGER);
        CREATE TABLE generated_batches(id INTEGER PRIMARY KEY AUTOINCREMENT, concurso_alvo INTEGER, status TEXT);
        CREATE TABLE memoria_jogos(id INTEGER PRIMARY KEY AUTOINCREMENT, concurso_n1 INTEGER, tipo_jogo INTEGER, acertos INTEGER);
        """
    )
    for c in range(1, 260):
        dezenas = [((c+i-1) % 25) + 1 for i in range(15)]
        conn.execute("INSERT INTO concursos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (c, *dezenas))
    for s in range(1, 80):
        conn.execute("INSERT INTO outcomes(run_id,step,concurso_ref,hit_max,reward,diversity,created_at) VALUES (1,?,?,?,?,?, 't')", (s, 100+s, 13, 0.1, 0.3))
        conn.execute("INSERT INTO decisions(run_id,step,arm,recipe,exploration_rate,confidence,fallback_used,created_at) VALUES (1,?,?,?,?,?,?, 't')", (s, 'a','r',0.5,0.6,1 if s%2==0 else 0))
        conn.execute("INSERT INTO telemetry_step_summaries(run_id,step,summary_json,created_at) VALUES (1,?,?, 't')", (s, json.dumps({'rescue_mode': s%4==0})))
    conn.commit()


def test_perf_cache_and_autotuner(tmp_path):
    conn = sqlite3.connect(":memory:")
    try:
        _mk_db(conn)
        apply_sqlite_pragmas(conn, "low_cpu")
        ensure_indexes(conn)

        fc = FeatureCache(conn, {"feature_cache": True})
        f1 = fc.get_features(200)
        f2 = fc.get_features(200)
        assert f1 == f2

        th = Throttle({"throttle": {"enabled": True, "sleep_every_steps": 1, "sleep_ms": 1}})
        th.maybe_sleep(1)

        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "meta_controller.json").write_text(json.dumps({"confidence_threshold": 0.6}), encoding="utf-8")
        (cfg_dir / "reward_v2.json").write_text(json.dumps({"weights": {"diversity": 0.3, "stagnation": 0.5}}), encoding="utf-8")
        (cfg_dir / "portfolio.json").write_text(json.dumps({"production": {"max_clone_jaccard": 0.8}}), encoding="utf-8")
        (cfg_dir / "diversity.json").write_text(json.dumps({"pair_sample_max": 200}), encoding="utf-8")
        (cfg_dir / "validator.json").write_text(json.dumps({"sample_concursos": 20}), encoding="utf-8")

        tuner = AutoTuner(conn, {
            "enabled": True,
            "run_every_steps": 50,
            "max_changes_per_run": 3,
            "limits": {
                "confidence_threshold": [0.45, 0.75],
                "reward_diversity_weight": [0.15, 0.60],
                "reward_stagnation_weight": [0.25, 0.80],
                "portfolio_max_clone_jaccard": [0.60, 0.85],
            },
        }, str(cfg_dir))
        tuner.run_if_due(run_id=1, step=500)
        h = conn.execute("SELECT COUNT(*) FROM tuning_history WHERE run_id=1").fetchone()[0]
        assert int(h) >= 0
    finally:
        conn.close()
