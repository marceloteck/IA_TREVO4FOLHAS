import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from training.reporting.report_html import generate_html_report
from training.reporting.telemetry_writer import TelemetryWriter


def _mk_min_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE runs (id INTEGER PRIMARY KEY, started_at TEXT, mode TEXT, config_hash TEXT, seed INTEGER, status TEXT);
        CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, step INTEGER, arm TEXT, recipe TEXT, exploration_rate REAL, confidence REAL, fallback_used INTEGER, created_at TEXT);
        CREATE TABLE outcomes (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, step INTEGER, concurso_ref INTEGER, hit_max INTEGER, reward REAL, diversity REAL, created_at TEXT);
        """
    )
    conn.execute("INSERT INTO runs VALUES (1,'2024-01-01','backtest','h',123,'finished')")
    for s in range(1, 21):
        conn.execute("INSERT INTO decisions(run_id,step,arm,recipe,exploration_rate,confidence,fallback_used,created_at) VALUES (1,?,?,?,?,?,?,?)", (s, f"a{s%3}", f"r{s%4}", 0.5, 0.7, s % 2, 't'))
        conn.execute("INSERT INTO outcomes(run_id,step,concurso_ref,hit_max,reward,diversity,created_at) VALUES (1,?,?,?,?,?,?)", (s, 100 + s, 13 + (s % 3), 0.2 * s, 0.4, 't'))
    conn.commit()
    return conn


def test_reporting_cli_html_and_artifacts(tmp_path):
    db = tmp_path / "reporting.db"
    conn = _mk_min_db(db)
    try:
        tw = TelemetryWriter(conn, {"enabled": True})
        tw.log_run_artifact(1, "config_hash", "abc")
        tw.log_run_artifact(1, "seed", "123")
        tw.log_summary_step(1, 20, {"mode": "production", "reward": 1.2, "learning_monitor": {"status": "learning", "trend": {"delta_reward": 0.2}, "baseline": {"delta_q14_vs_baseline": 0.04}, "policy": {"force_mode": None, "rescue_mode": False}}})
        tw.log_experiment({"run_id": 1, "passes": True, "candidate_name": "x", "baseline_name": "b"})

        out = tmp_path / "run_1.html"
        generate_html_report(conn, 1, out, top_n=5)
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "Linha do tempo de status" in content
        assert "Histórico de mudanças de modo" in content
    finally:
        conn.close()

    env = dict(os.environ)
    env["DB_PATH"] = str(db)
    r = subprocess.run(
        [sys.executable, "training/reporting/report_cli.py", "--last-run"],
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Run 1" in r.stdout
    assert "Top arms" in r.stdout
