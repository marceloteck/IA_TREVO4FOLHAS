from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from training.reporting import queries
from training.tuning.config_writer import safe_update_json
from training.tuning.tuning_rules import propose_changes


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AutoTuner:
    def __init__(self, db_conn, cfg: dict, config_dir: str):
        self.conn: sqlite3.Connection = db_conn
        self.cfg = dict(cfg or {})
        self.config_dir = Path(config_dir)
        self.enabled = bool(self.cfg.get("enabled", False))
        self.run_every = max(50, int(self.cfg.get("run_every_steps", 500)))
        self.max_changes = max(1, int(self.cfg.get("max_changes_per_run", 3)))
        self.limits = dict(self.cfg.get("limits", {}))
        self.last_step_by_run: dict[int, int] = {}
        self._ensure()

    def _ensure(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tuning_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id INTEGER,
              step INTEGER,
              created_at TEXT,
              changes_json TEXT,
              reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tuning_run ON tuning_history(run_id);
            """
        )
        self.conn.commit()

    def _current_values(self) -> dict:
        def _load(name, default):
            p = self.config_dir / name
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return default

        meta = _load("meta_controller.json", {})
        reward = _load("reward_v2.json", {})
        portfolio = _load("portfolio.json", {})
        diversity = _load("diversity.json", {})
        validator = _load("validator.json", {})
        return {
            "confidence_threshold": float(meta.get("confidence_threshold", 0.55)),
            "reward_diversity_weight": float(reward.get("weights", {}).get("diversity", 0.35)),
            "reward_stagnation_weight": float(reward.get("weights", {}).get("stagnation", 0.55)),
            "portfolio_max_clone_jaccard": float(portfolio.get("production", {}).get("max_clone_jaccard", 0.78)),
            "pair_sample_max": int(diversity.get("pair_sample_max", 200)),
            "sample_concursos": int(validator.get("sample_concursos", 20)),
        }

    def run_if_due(self, run_id: int, step: int):
        if not self.enabled:
            return
        last = self.last_step_by_run.get(int(run_id), 0)
        if int(step) - last < self.run_every:
            return

        metrics = queries.get_tuning_metrics(self.conn, int(run_id))
        current = self._current_values()
        changes, reason = propose_changes(metrics, current, self.limits)
        if not changes:
            self.last_step_by_run[int(run_id)] = int(step)
            return

        # limit breadth
        flat = []
        for cfg_name in list(changes.keys()):
            flat.append(cfg_name)
        for cfg_name in flat[self.max_changes :]:
            del changes[cfg_name]

        mapping = {
            "meta_controller": "meta_controller.json",
            "reward_v2": "reward_v2.json",
            "portfolio": "portfolio.json",
            "diversity": "diversity.json",
            "validator": "validator.json",
        }
        for key, payload in changes.items():
            fn = mapping.get(key)
            if fn:
                safe_update_json(str(self.config_dir / fn), payload, backup=True)

        self.conn.execute(
            "INSERT INTO tuning_history(run_id, step, created_at, changes_json, reason) VALUES (?, ?, ?, ?, ?)",
            (int(run_id), int(step), now_str(), json.dumps(changes, ensure_ascii=False), str(reason)),
        )
        self.conn.commit()
        self.last_step_by_run[int(run_id)] = int(step)
