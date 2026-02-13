from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TelemetryWriter:
    def __init__(self, db_conn, cfg: dict):
        self.conn: sqlite3.Connection = db_conn
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                started_at TEXT,
                ended_at TEXT,
                kind TEXT,
                candidate_name TEXT,
                baseline_name TEXT,
                window_steps INTEGER,
                status TEXT,
                candidate_score_mean REAL,
                baseline_score_mean REAL,
                passes INTEGER,
                notes TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_exp_run ON experiments(run_id);

            CREATE TABLE IF NOT EXISTS run_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                key TEXT,
                value TEXT,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_art_run ON run_artifacts(run_id);

            CREATE TABLE IF NOT EXISTS telemetry_step_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                step INTEGER,
                summary_json TEXT,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tsum_run_step ON telemetry_step_summaries(run_id, step);
            """
        )
        self.conn.commit()

    def log_run_artifact(self, run_id: int, key: str, value: str):
        if not self.enabled:
            return
        self.conn.execute(
            "INSERT INTO run_artifacts(run_id, key, value, created_at) VALUES (?, ?, ?, ?)",
            (int(run_id), str(key), str(value), now_str()),
        )
        self.conn.commit()

    def log_experiment(self, exp: dict):
        if not self.enabled:
            return
        self.conn.execute(
            """
            INSERT INTO experiments(
                run_id, started_at, ended_at, kind, candidate_name, baseline_name,
                window_steps, status, candidate_score_mean, baseline_score_mean, passes, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(exp.get("run_id", 0)),
                str(exp.get("started_at", now_str())),
                str(exp.get("ended_at", now_str())),
                str(exp.get("kind", "validator")),
                str(exp.get("candidate_name", "unknown")),
                str(exp.get("baseline_name", "global+recent")),
                int(exp.get("window_steps", 0)),
                str(exp.get("status", "finished")),
                float(exp.get("candidate_score_mean", 0.0)),
                float(exp.get("baseline_score_mean", 0.0)),
                1 if bool(exp.get("passes", False)) else 0,
                str(exp.get("notes", "")),
            ),
        )
        self.conn.commit()

    def log_summary_step(self, run_id: int, step: int, summary: dict):
        if not self.enabled:
            return
        self.conn.execute(
            "INSERT INTO telemetry_step_summaries(run_id, step, summary_json, created_at) VALUES (?, ?, ?, ?)",
            (int(run_id), int(step), json.dumps(summary, ensure_ascii=False), now_str()),
        )
        self.conn.commit()
