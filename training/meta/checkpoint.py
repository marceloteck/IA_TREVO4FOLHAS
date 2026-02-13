from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from training.meta.state_serialization import compute_hash, serialize_state, validate_state


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class CheckpointManager:
    def __init__(self, db_conn: sqlite3.Connection, cfg: dict):
        self.conn = db_conn
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.max_keep = max(10, int(self.cfg.get("max_keep_checkpoints", 50)))
        self._ensure_table()

    def _ensure_table(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                step INTEGER,
                concurso_ref INTEGER,
                created_at TEXT,
                state_json TEXT,
                state_hash TEXT,
                is_valid INTEGER DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoints_run_step ON checkpoints(run_id, step);
            """
        )
        self.conn.commit()

    def _prune(self, run_id: int) -> None:
        rows = self.conn.execute(
            "SELECT id FROM checkpoints WHERE run_id=? AND is_valid=1 ORDER BY step DESC, id DESC",
            (int(run_id),),
        ).fetchall()
        if len(rows) <= self.max_keep:
            return
        to_delete = [int(r[0]) for r in rows[self.max_keep :]]
        self.conn.executemany("DELETE FROM checkpoints WHERE id=?", [(x,) for x in to_delete])

    def save(self, state: dict):
        if not self.enabled:
            return
        state_json = serialize_state(state)
        state_hash = compute_hash(state_json)
        run_id = int(state.get("run_id", 0))
        step = int(state.get("step", 0))
        concurso_ref = int(state.get("concurso_ref", 0))
        try:
            self.conn.execute("BEGIN")
            self.conn.execute(
                """
                INSERT INTO checkpoints(run_id, step, concurso_ref, created_at, state_json, state_hash, is_valid)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (run_id, step, concurso_ref, now_str(), state_json, state_hash),
            )
            self._prune(run_id)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _load_rows(self, run_id: int):
        return self.conn.execute(
            """
            SELECT id, state_json, state_hash
            FROM checkpoints
            WHERE run_id=?
            ORDER BY step DESC, id DESC
            """,
            (int(run_id),),
        ).fetchall()

    def load_latest_valid(self, run_id: int) -> dict | None:
        if not self.enabled:
            return None
        rows = self._load_rows(run_id)
        for ck_id, state_json, state_hash in rows:
            if state_json and state_hash and validate_state(str(state_json), str(state_hash)):
                try:
                    return json.loads(str(state_json))
                except Exception:
                    pass
            self.conn.execute("UPDATE checkpoints SET is_valid=0 WHERE id=?", (int(ck_id),))
            self.conn.commit()
        return None

    def load_latest_valid_any_running(self) -> dict | None:
        row = self.conn.execute(
            "SELECT id FROM runs WHERE status='running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        return self.load_latest_valid(int(row[0]))
