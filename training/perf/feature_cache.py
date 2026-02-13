from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from training.meta.context_features import extract_context_features


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FeatureCache:
    def __init__(self, db_conn, cfg: dict):
        self.conn: sqlite3.Connection = db_conn
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("feature_cache", True))
        self._ensure()

    def _ensure(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_cache (
              concurso_ref INTEGER PRIMARY KEY,
              features_json TEXT,
              created_at TEXT
            )
            """
        )
        self.conn.commit()

    def get_features(self, concurso_ref: int, overrides: dict | None = None) -> dict:
        if not self.enabled:
            return extract_context_features(self.conn, int(concurso_ref), overrides=overrides)
        row = self.conn.execute("SELECT features_json FROM feature_cache WHERE concurso_ref=?", (int(concurso_ref),)).fetchone()
        if row and row[0]:
            try:
                d = json.loads(str(row[0]))
                if overrides:
                    d.update({k: v for k, v in overrides.items() if v is not None})
                return d
            except Exception:
                pass
        d = extract_context_features(self.conn, int(concurso_ref), overrides=overrides)
        self.conn.execute(
            "INSERT OR REPLACE INTO feature_cache(concurso_ref, features_json, created_at) VALUES (?, ?, ?)",
            (int(concurso_ref), json.dumps(d, ensure_ascii=False), now_str()),
        )
        self.conn.commit()
        return d
