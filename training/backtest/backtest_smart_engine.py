from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import numpy as np
import pickle
import random
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.backtest.backtest_engine import (
    build_context,
    fetch_all_concursos,
    fetch_result,
    insert_memoria_forte,
    insert_tentativa,
    register_brains_auto,
    safe_table_exists,
)
from training.core.brain_hub import BrainHub
from training.meta.context_features import extract_context_features
from training.meta.diversity import portfolio_diversity
from training.meta.ab_testing import ABTestingManager
from training.meta.checkpoint import CheckpointManager
from training.meta.meta_controller import MetaController
from training.meta.mode_manager import ModeManager
from training.meta.model_store import ModelStore
from training.meta.portfolio_builder import PortfolioBuilder
from training.meta.promotion import PromotionManager
from training.meta.regime_detector import detect_regime as detect_regime_v2
from training.meta.reward_v2 import compute_reward_v2
from training.meta.stagnation import StagnationTracker
from training.meta.learning_monitor import LearningMonitor
from training.memory.memory_audit import ensure_memory_tables
from training.memory.memory_refiner import MemoryRefiner
from training.perf.feature_cache import FeatureCache
from training.perf.sqlite_optimize import apply_sqlite_pragmas, ensure_indexes
from training.perf.throttle import Throttle
from training.reporting.report_html import generate_html_report
from training.reporting.run_artifacts import compute_config_hash, try_get_git_commit
from training.reporting.telemetry_writer import TelemetryWriter
from training.validation.validator import StrategyValidator
from training.tuning.auto_tuner import AutoTuner
from training.utils.comparador import contar_acertos
from training.utils.progress import Heartbeat, ProgressPrinter, StepTimer


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}", flush=True)


def _status_icon(status: str) -> str:
    return {
        "learning": "🟢",
        "stable": "🟡",
        "regressing": "🔴",
        "warmup": "⚪",
    }.get(str(status), "⚪")


def _status_label(status: str) -> str:
    return {
        "learning": "APRENDENDO",
        "stable": "ESTÁVEL",
        "regressing": "REGREDINDO",
        "warmup": "WARMUP",
    }.get(str(status), "WARMUP")


def load_json_config(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return dict(default)

def _encode_obj(obj: Any) -> str:
    return base64.b64encode(pickle.dumps(obj)).decode("ascii")


def _decode_obj(blob: str) -> Any:
    return pickle.loads(base64.b64decode(blob.encode("ascii")))


def _current_brain_mask(hub: BrainHub) -> List[str]:
    out: List[str] = []
    for b in getattr(hub, "brains", []):
        if bool(getattr(b, "enabled", False)):
            out.append(str(getattr(b, "id", "")))
    return out


def _restore_brain_mask(hub: BrainHub, mask: Sequence[str]) -> None:
    allow = set(str(x) for x in (mask or []))
    for b in getattr(hub, "brains", []):
        setattr(b, "enabled", str(getattr(b, "id", "")) in allow)


def _latest_open_run_id(conn: sqlite3.Connection, table: str, id_col: str = "id", where: str = "") -> int | None:
    q = f"SELECT {id_col} FROM {table} "
    if where:
        q += f"WHERE {where} "
    q += f"ORDER BY {id_col} DESC LIMIT 1"
    row = conn.execute(q).fetchone()
    return int(row[0]) if row and row[0] is not None else None


@dataclass(frozen=True)
class SmartArm:
    name: str
    janela: int
    top_n: int
    base_per_brain: int
    boost_top_brains: int


@dataclass
class ArmStats:
    pulls: int = 0
    reward_sum: float = 0.0
    best_hit: int = 0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / float(self.pulls) if self.pulls > 0 else 0.0


@dataclass
class SmartRecipe:
    name: str
    members: List[str]
    boosts: Dict[str, int] = field(default_factory=dict)
    generation: int = 0
    status: str = "seed"


@dataclass
class RecipeStats:
    pulls: int = 0
    reward_sum: float = 0.0
    q14_sum: int = 0
    q15_sum: int = 0
    best_hit: int = 0

    @property
    def mean_reward(self) -> float:
        return self.reward_sum / float(self.pulls) if self.pulls > 0 else 0.0


def ensure_smart_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_backtest_smart (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ultimo_concurso_processado INTEGER,
            timestamp TEXT
        );

        CREATE TABLE IF NOT EXISTS backtest_smart_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            target_min_hit INTEGER NOT NULL DEFAULT 14,
            target_max_hit INTEGER NOT NULL DEFAULT 15,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS backtest_smart_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            concurso_n INTEGER NOT NULL,
            concurso_n1 INTEGER NOT NULL,
            arm_name TEXT NOT NULL,
            recipe_name TEXT,
            regime TEXT,
            brains_ativos INTEGER NOT NULL,
            reward REAL NOT NULL,
            melhor_acerto INTEGER NOT NULL,
            q14 INTEGER NOT NULL,
            q15 INTEGER NOT NULL,
            detalhes_json TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES backtest_smart_runs(id)
        );

        CREATE TABLE IF NOT EXISTS backtest_smart_recipes (
            name TEXT PRIMARY KEY,
            generation INTEGER NOT NULL,
            status TEXT NOT NULL,
            members_json TEXT NOT NULL,
            boosts_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS backtest_smart_recipe_trials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            recipe_name TEXT NOT NULL,
            concurso_n INTEGER NOT NULL,
            reward REAL NOT NULL,
            q14 INTEGER NOT NULL,
            q15 INTEGER NOT NULL,
            best_hit INTEGER NOT NULL,
            regime TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES backtest_smart_runs(id)
        );

        CREATE TABLE IF NOT EXISTS backtest_smart_hypotheses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            hypothesis_json TEXT NOT NULL,
            status TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_backtest_smart_steps_run ON backtest_smart_steps(run_id);
        CREATE INDEX IF NOT EXISTS idx_backtest_smart_steps_concurso ON backtest_smart_steps(concurso_n);
        CREATE INDEX IF NOT EXISTS idx_backtest_recipe_trials_run ON backtest_smart_recipe_trials(run_id);
        CREATE INDEX IF NOT EXISTS idx_backtest_recipe_trials_recipe ON backtest_smart_recipe_trials(recipe_name);
        CREATE INDEX IF NOT EXISTS idx_backtest_hypotheses_kind ON backtest_smart_hypotheses(kind);
        """
    )
    conn.commit()


def ensure_meta_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            mode TEXT,
            config_hash TEXT,
            seed INTEGER,
            status TEXT
        );

        CREATE TABLE IF NOT EXISTS context_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            step INTEGER,
            concurso_ref INTEGER,
            features_json TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            step INTEGER,
            arm TEXT,
            recipe TEXT,
            exploration_rate REAL,
            confidence REAL,
            fallback_used INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            step INTEGER,
            concurso_ref INTEGER,
            hit_max INTEGER,
            reward REAL,
            diversity REAL,
            created_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at);
        CREATE INDEX IF NOT EXISTS idx_ctx_run_step ON context_snapshots(run_id, step);
        CREATE INDEX IF NOT EXISTS idx_decisions_run_step ON decisions(run_id, step);
        CREATE INDEX IF NOT EXISTS idx_outcomes_run_step ON outcomes(run_id, step);
        """
    )
    conn.commit()


def start_meta_run(conn: sqlite3.Connection, mode: str, config_payload: Dict[str, Any], seed: int) -> int:
    ensure_meta_tables(conn)
    cfg = json.dumps(config_payload, sort_keys=True, ensure_ascii=False)
    cfg_hash = hashlib.sha1(cfg.encode("utf-8")).hexdigest()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO runs(started_at, mode, config_hash, seed, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (now_str(), str(mode), cfg_hash, int(seed), "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_meta_run(conn: sqlite3.Connection, run_id: int, status: str = "finished") -> None:
    conn.execute("UPDATE runs SET status=? WHERE id=?", (str(status), int(run_id)))
    conn.commit()


def get_smart_checkpoint(conn: sqlite3.Connection) -> int:
    ensure_smart_tables(conn)
    row = conn.execute("SELECT ultimo_concurso_processado FROM checkpoint_backtest_smart WHERE id=1").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def set_smart_checkpoint(conn: sqlite3.Connection, concurso_n: int) -> None:
    ensure_smart_tables(conn)
    conn.execute(
        """
        INSERT INTO checkpoint_backtest_smart (id, ultimo_concurso_processado, timestamp)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ultimo_concurso_processado=excluded.ultimo_concurso_processado,
            timestamp=excluded.timestamp
        """,
        (int(concurso_n), now_str()),
    )
    conn.commit()


def start_smart_run(conn: sqlite3.Connection, run_name: str, notes: str = "") -> int:
    ensure_smart_tables(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO backtest_smart_runs(run_name, started_at, target_min_hit, target_max_hit, notes)
        VALUES (?, ?, 14, 15, ?)
        """,
        (str(run_name), now_str(), str(notes)),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_smart_run(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute("UPDATE backtest_smart_runs SET finished_at=? WHERE id=?", (now_str(), int(run_id)))
    conn.commit()


def upsert_recipe(conn: sqlite3.Connection, recipe: SmartRecipe) -> None:
    ts = now_str()
    conn.execute(
        """
        INSERT INTO backtest_smart_recipes(name, generation, status, members_json, boosts_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            generation=excluded.generation,
            status=excluded.status,
            members_json=excluded.members_json,
            boosts_json=excluded.boosts_json,
            updated_at=excluded.updated_at
        """,
        (
            recipe.name,
            int(recipe.generation),
            str(recipe.status),
            json.dumps(sorted(set(recipe.members)), ensure_ascii=False),
            json.dumps({str(k): int(v) for k, v in recipe.boosts.items()}, ensure_ascii=False),
            ts,
            ts,
        ),
    )
    conn.commit()


def register_hypothesis(
    conn: sqlite3.Connection,
    run_id: int | None,
    kind: str,
    title: str,
    payload: Dict[str, Any],
    status: str = "candidate",
    score: float = 0.0,
) -> None:
    ts = now_str()
    conn.execute(
        """
        INSERT INTO backtest_smart_hypotheses(run_id, kind, title, hypothesis_json, status, score, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(run_id) if run_id is not None else None,
            str(kind),
            str(title),
            json.dumps(payload, ensure_ascii=False),
            str(status),
            float(score),
            ts,
            ts,
        ),
    )
    conn.commit()


def load_recipes(conn: sqlite3.Connection, available_brains: Sequence[str]) -> Dict[str, SmartRecipe]:
    ensure_smart_tables(conn)
    recipes: Dict[str, SmartRecipe] = {}
    rows = conn.execute(
        "SELECT name, generation, status, members_json, boosts_json FROM backtest_smart_recipes ORDER BY generation, name"
    ).fetchall()
    avail = set(str(b) for b in available_brains)
    for name, generation, status, members_json, boosts_json in rows:
        members = [m for m in json.loads(members_json or "[]") if str(m) in avail]
        if not members:
            continue
        boosts_raw = json.loads(boosts_json or "{}")
        boosts = {str(k): int(v) for k, v in boosts_raw.items() if str(k) in avail}
        recipes[str(name)] = SmartRecipe(str(name), members=members, boosts=boosts, generation=int(generation or 0), status=str(status or "seed"))
    return recipes


def ensure_seed_recipes(conn: sqlite3.Connection, loaded_brains: Sequence[str]) -> Dict[str, SmartRecipe]:
    ids = [str(x) for x in loaded_brains]
    seeds = {
        "seed_all": SmartRecipe("seed_all", members=ids, generation=0, status="seed"),
        "seed_conservador": SmartRecipe("seed_conservador", members=ids[: max(8, int(len(ids) * 0.55))], generation=0, status="seed"),
        "seed_agressivo": SmartRecipe("seed_agressivo", members=ids[: max(10, int(len(ids) * 0.80))], generation=0, status="seed"),
    }
    for r in seeds.values():
        upsert_recipe(conn, r)
    return load_recipes(conn, ids)


def fetch_brain_phase_scores(conn: sqlite3.Connection, recent_window: int) -> Dict[str, float]:
    if not safe_table_exists(conn, "cerebro_performance"):
        return {}

    perf_cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(cerebro_performance)").fetchall()}
    concurso_col = "concurso_n" if "concurso_n" in perf_cols else ("concurso" if "concurso" in perf_cols else None)
    if concurso_col is None:
        return {}

    # Esquema novo/legado: (brain_id, acertos) vs (cerebro_id, qtd_14/qtd_15).
    if {"brain_id", "acertos"}.issubset(perf_cols):
        group_expr = "brain_id"
        q15_expr = "SUM(CASE WHEN acertos >= 15 THEN 1 ELSE 0 END)"
        q14_expr = "SUM(CASE WHEN acertos >= 14 THEN 1 ELSE 0 END)"
    elif {"cerebro_id", "qtd_14", "qtd_15"}.issubset(perf_cols) and safe_table_exists(conn, "cerebros"):
        group_expr = "c.brain_id"
        q15_expr = "COALESCE(SUM(p.qtd_15), 0)"
        q14_expr = "COALESCE(SUM(p.qtd_14), 0)"
    else:
        return {}

    max_row = conn.execute(f"SELECT MAX({concurso_col}) FROM cerebro_performance").fetchone()
    max_n = int(max_row[0]) if max_row and max_row[0] is not None else 0
    min_n = max(1, max_n - int(recent_window) + 1)

    if group_expr == "brain_id":
        rows = conn.execute(
            f"""
            SELECT {group_expr},
                   {q15_expr} AS q15,
                   {q14_expr} AS q14,
                   COUNT(*) AS jogos
              FROM cerebro_performance
             WHERE {concurso_col} >= ?
             GROUP BY {group_expr}
            """,
            (int(min_n),),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT {group_expr},
                   {q15_expr} AS q15,
                   {q14_expr} AS q14,
                   COALESCE(SUM(p.jogos_gerados), 0) AS jogos
              FROM cerebro_performance p
              JOIN cerebros c ON c.id = p.cerebro_id
             WHERE p.{concurso_col} >= ?
             GROUP BY {group_expr}
            """,
            (int(min_n),),
        ).fetchall()

    scores: Dict[str, float] = {}
    for brain_id, q15, q14, jogos in rows:
        jogos = max(1, int(jogos or 0))
        scores[str(brain_id)] = (int(q15 or 0) * 6.0 + int(q14 or 0) * 2.0) / float(jogos)
    return scores


def detect_regime(context: Dict[str, Any]) -> str:
    hist = context.get("historico_recente", [])
    if len(hist) < 4:
        return "neutro"
    sums = [sum(r) for r in hist[-8:]]
    repeat_rates: List[float] = []
    for i in range(1, min(len(hist), 8)):
        a, b = set(hist[-i]), set(hist[-i - 1])
        repeat_rates.append(len(a & b) / 15.0)
    avg_repeat = sum(repeat_rates) / float(len(repeat_rates) or 1)
    vol = max(sums) - min(sums)

    if avg_repeat >= 0.56 and vol <= 45:
        return "estavel"
    if avg_repeat <= 0.42 and vol >= 65:
        return "volatil"
    if sums[-1] >= sum(sums) / float(len(sums)):
        return "aquecido"
    return "frio"


def arm_regime_bonus(arm: SmartArm, regime: str) -> float:
    if regime == "estavel":
        return 0.20 if arm.janela >= 260 else 0.05
    if regime == "volatil":
        return 0.20 if arm.janela <= 200 or arm.top_n >= 220 else 0.05
    if regime == "aquecido":
        return 0.15 if arm.base_per_brain >= 80 else 0.02
    if regime == "frio":
        return 0.12 if arm.boost_top_brains >= 25 else 0.01
    return 0.0


def build_per_brain_map(
    brain_ids: Sequence[str],
    phase_scores: Dict[str, float],
    base_per_brain: int,
    boost_top_brains: int,
    recipe_boosts: Dict[str, int] | None = None,
) -> Dict[str, int]:
    if not brain_ids:
        return {}
    recipe_boosts = recipe_boosts or {}
    ordered = sorted(brain_ids, key=lambda b: phase_scores.get(str(b), 0.0), reverse=True)
    top_set = set(ordered[: max(1, int(len(ordered) * 0.35))])
    out: Dict[str, int] = {}
    for bid in ordered:
        n = int(base_per_brain)
        if bid in top_set:
            n += int(boost_top_brains)
        n += int(round(float(phase_scores.get(str(bid), 0.0)) * 15.0))
        n += int(recipe_boosts.get(str(bid), 0))
        out[str(bid)] = max(20, n)
    return out


def choose_arm_ucb(
    arms: Sequence[SmartArm],
    stats: Dict[str, ArmStats],
    total_steps: int,
    c: float,
    regime: str = "neutro",
) -> SmartArm:
    for arm in arms:
        if stats[arm.name].pulls == 0:
            return arm
    total = max(1, int(total_steps))
    return max(
        arms,
        key=lambda arm: stats[arm.name].mean_reward
        + float(c) * math.sqrt(math.log(total) / float(stats[arm.name].pulls))
        + arm_regime_bonus(arm, regime),
    )


def choose_recipe_ucb(recipes: Dict[str, SmartRecipe], stats: Dict[str, RecipeStats], total_steps: int, c: float) -> SmartRecipe:
    ordered = [recipes[k] for k in sorted(recipes.keys())]
    for rec in ordered:
        if stats[rec.name].pulls == 0 and rec.status in {"seed", "candidate", "promoted"}:
            return rec
    total = max(1, int(total_steps))
    valid = [r for r in ordered if r.status in {"seed", "candidate", "promoted", "parked"}]
    return max(
        valid,
        key=lambda rec: stats[rec.name].mean_reward + float(c) * math.sqrt(math.log(total) / float(max(1, stats[rec.name].pulls))),
    )


def _set_enabled_brains(hub: BrainHub, allowed: Sequence[str]) -> int:
    allow = set(str(x) for x in allowed)
    active = 0
    for b in getattr(hub, "brains", []):
        enabled = str(getattr(b, "id", "")) in allow
        setattr(b, "enabled", enabled)
        if enabled:
            active += 1
    return active


def _recipe_active_members(recipe: SmartRecipe, loaded_ids: Sequence[str], phase_scores: Dict[str, float]) -> List[str]:
    valid = [bid for bid in recipe.members if bid in loaded_ids]
    if not valid:
        return list(loaded_ids)
    ordered = sorted(valid, key=lambda b: phase_scores.get(str(b), 0.0), reverse=True)
    keep = max(6, int(round(len(ordered) * 0.75)))
    return ordered[:keep]


def _augment_members(base: List[str], forced: Sequence[str] | None = None, experimental: Sequence[str] | None = None) -> List[str]:
    out = list(base)
    for group in (forced or [], experimental or []):
        if str(group) not in out:
            out.append(str(group))
    return out


def _build_candidate_records(cands: List[Dict[str, Any]], tipo: int, arm: SmartArm, recipe: SmartRecipe, ultimo: set[int]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for c in cands:
        dezenas = sorted(set(int(x) for x in c.get("jogo", []) if x is not None))
        if len(dezenas) != int(tipo):
            continue
        even = sum(1 for d in dezenas if d % 2 == 0)
        repetidas = len(set(dezenas) & set(ultimo)) if ultimo else 0
        records.append(
            {
                "dezenas": dezenas,
                "score": float(c.get("score", 0.0)),
                "origem": f"{arm.name}:{recipe.name}:{c.get('brain_id', 'unknown')}",
                "features": {
                    "even": int(even),
                    "sum": int(sum(dezenas)),
                    "repeated": int(repetidas),
                },
                "raw": c,
            }
        )
    return records


def evolve_recipe(
    recipes: Dict[str, SmartRecipe],
    recipe_stats: Dict[str, RecipeStats],
    loaded_ids: Sequence[str],
    phase_scores: Dict[str, float],
    step: int,
    max_members: int,
) -> SmartRecipe:
    ranked = sorted(
        recipes.values(),
        key=lambda r: (recipe_stats.get(r.name, RecipeStats()).mean_reward, recipe_stats.get(r.name, RecipeStats()).q15_sum),
        reverse=True,
    )
    parent_a = ranked[0] if ranked else SmartRecipe("seed_all", members=list(loaded_ids))
    parent_b = ranked[1] if len(ranked) > 1 else parent_a
    pool = list(dict.fromkeys(parent_a.members + parent_b.members))
    if len(pool) < 8:
        pool = list(dict.fromkeys(pool + list(loaded_ids)))
    sorted_pool = sorted(pool, key=lambda b: phase_scores.get(str(b), 0.0), reverse=True)
    n_members = min(max_members, max(8, int(round(len(sorted_pool) * 0.72))))
    members = sorted_pool[:n_members]

    if len(loaded_ids) > n_members and random.random() < 0.65:
        swaps = random.randint(1, 2)
        outside = [b for b in loaded_ids if b not in members]
        for _ in range(swaps):
            if not outside or not members:
                break
            out_idx = random.randrange(len(members))
            in_id = outside.pop(random.randrange(len(outside)))
            members[out_idx] = in_id

    boosts: Dict[str, int] = {}
    for bid in members[: max(3, int(len(members) * 0.25))]:
        boosts[str(bid)] = int(4 + round(float(phase_scores.get(str(bid), 0.0)) * 8.0))

    return SmartRecipe(
        name=f"auto_recipe_{step}",
        members=sorted(set(members)),
        boosts=boosts,
        generation=step,
        status="candidate",
    )


def revive_parked_recipes(
    recipes: Dict[str, SmartRecipe],
    recipe_stats: Dict[str, RecipeStats],
    phase_scores: Dict[str, float],
    limit: int = 1,
) -> List[str]:
    revived: List[str] = []
    candidates = [r for r in recipes.values() if r.status == "parked"]
    candidates = sorted(candidates, key=lambda r: recipe_stats.get(r.name, RecipeStats()).q15_sum, reverse=True)
    for rec in candidates:
        if len(revived) >= int(limit):
            break
        top_phase = max((phase_scores.get(b, 0.0) for b in rec.members), default=0.0)
        if top_phase >= 0.25:
            rec.status = "candidate"
            revived.append(rec.name)
    return revived


def update_recipe_status(recipe: SmartRecipe, stats: RecipeStats, min_pulls: int, promote_reward: float) -> SmartRecipe:
    if stats.pulls < int(min_pulls):
        return recipe
    if stats.mean_reward >= float(promote_reward):
        recipe.status = "promoted"
    elif stats.mean_reward <= max(0.1, float(promote_reward) * 0.40):
        recipe.status = "parked"
    else:
        recipe.status = "candidate"
    return recipe


def compute_reward(
    q14: int,
    q15: int,
    best: int,
    regime: str,
    repeat_rate: float,
    reward_q15: float,
    reward_q14: float,
) -> float:
    reward = float(q15) * float(reward_q15) + float(q14) * float(reward_q14)
    if best < 14:
        reward -= 2.0
    if regime == "estavel" and repeat_rate >= 0.50:
        reward += 0.35
    if regime == "volatil" and repeat_rate <= 0.45:
        reward += 0.35
    return reward


def run_step(
    conn: sqlite3.Connection,
    hub: BrainHub,
    concurso_n: int,
    arm: SmartArm,
    recipe: SmartRecipe,
    recent_window: int,
    avaliar_top_k: int,
    min_mem: int,
    reward_q15: float,
    reward_q14: float,
    mode: str = "production",
    portfolio_builder: PortfolioBuilder | None = None,
    portfolio_cfg: Dict[str, Any] | None = None,
    forced_brains: Sequence[str] | None = None,
    experimental_brains: Sequence[str] | None = None,
    memory_refiner_cfg: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    result_n1 = fetch_result(conn, concurso_n + 1)
    if not result_n1:
        return {
            "reward": 0.0,
            "legacy_reward": 0.0,
            "q14": 0,
            "q15": 0,
            "melhor_acerto": 0,
            "active": 0,
            "regime": "neutro",
            "repeat_rate": 0.0,
            "hits_distribution": {"12": 0, "13": 0, "14": 0, "15": 0},
            "evaluated_games": [],
        }

    context = build_context(conn, concurso_n, arm.janela)
    regime = detect_regime(context)
    ultimo = set(context.get("ultimo_resultado", []))
    phase_scores = fetch_brain_phase_scores(conn, recent_window=recent_window)
    loaded_ids = [str(getattr(b, "id", "unknown")) for b in getattr(hub, "brains", [])]

    active_ids = _recipe_active_members(recipe, loaded_ids, phase_scores)
    active_ids = _augment_members(active_ids, forced=forced_brains, experimental=experimental_brains)
    brains_ativos = _set_enabled_brains(hub, active_ids)
    per_brain_map = build_per_brain_map(active_ids, phase_scores, arm.base_per_brain, arm.boost_top_brains, recipe.boosts)

    t0 = time.time()
    c15 = hub.generate_games(context=context, size=15, per_brain=per_brain_map, top_n=arm.top_n)
    c18 = hub.generate_games(context=context, size=18, per_brain=per_brain_map, top_n=arm.top_n)
    dt = time.time() - t0

    c15 = (c15 or [])
    c18 = (c18 or [])

    prefer_gold = bool((memory_refiner_cfg or {}).get("prefer_gold_in_production", False)) and str(mode) == "production"
    if prefer_gold:
        gold_rows = conn.execute("SELECT dezenas_json FROM memoria_jogos_gold WHERE tipo_jogo IN (15,18) ORDER BY hit DESC, quality_score DESC LIMIT 5000").fetchall()
        gold_set = set(str(r[0]) for r in gold_rows)
        for cand in c15:
            key = json.dumps(sorted(set(int(x) for x in cand.get("jogo", []) if x is not None)), ensure_ascii=False)
            if key in gold_set:
                cand["score"] = float(cand.get("score", 0.0)) + 0.75
        for cand in c18:
            key = json.dumps(sorted(set(int(x) for x in cand.get("jogo", []) if x is not None)), ensure_ascii=False)
            if key in gold_set:
                cand["score"] = float(cand.get("score", 0.0)) + 0.75

    if portfolio_builder is not None and bool((portfolio_cfg or {}).get("enabled", False)):
        rec15 = _build_candidate_records(c15, 15, arm, recipe, ultimo)
        rec18 = _build_candidate_records(c18, 18, arm, recipe, ultimo)
        qmode = "research" if str(mode) == "research" else "production"
        chosen15 = portfolio_builder.build(rec15, int(avaliar_top_k), qmode, quotas={})
        chosen18 = portfolio_builder.build(rec18, int(avaliar_top_k), qmode, quotas={})
        set15 = {tuple(x) for x in chosen15}
        set18 = {tuple(x) for x in chosen18}
        c15 = [c for c in c15 if tuple(sorted(set(int(x) for x in c.get("jogo", []) if x is not None))) in set15]
        c18 = [c for c in c18 if tuple(sorted(set(int(x) for x in c.get("jogo", []) if x is not None))) in set18]
    else:
        c15 = c15[: int(avaliar_top_k)]
        c18 = c18[: int(avaliar_top_k)]

    q14 = q15 = mem = 0
    best = 0
    rep_sum = 0.0
    rep_count = 0
    hits_distribution = {"12": 0, "13": 0, "14": 0, "15": 0}
    evaluated_games: List[List[int]] = []
    tentativa = 1
    for tipo, cands in ((15, c15), (18, c18)):
        for c in cands:
            jogo = sorted(set(int(x) for x in c.get("jogo", []) if x is not None))
            if len(jogo) != tipo:
                continue
            acertos = int(contar_acertos(jogo, result_n1))
            evaluated_games.append(jogo)
            best = max(best, acertos)
            if acertos >= 12:
                k = str(min(15, acertos))
                if k in hits_distribution:
                    hits_distribution[k] += 1
            if acertos >= 14:
                q14 += 1
            if acertos >= 15:
                q15 += 1
            if ultimo:
                rep_sum += len(set(jogo) & ultimo) / float(len(ultimo))
                rep_count += 1

            insert_tentativa(
                conn=conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                tentativa=tentativa,
                dezenas=jogo,
                acertos=acertos,
                score=float(c.get("score", 0.0)),
                score_tag=f"smart:{arm.name}:{recipe.name}:{regime}",
                brain_id=str(c.get("brain_id", "unknown")),
                tempo_exec=dt,
                timestamp=now_str(),
            )
            tentativa += 1

            if insert_memoria_forte(
                conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                dezenas=jogo,
                acertos=acertos,
                peso=float(c.get("score", 0.0)),
                origem=f"smart:{arm.name}:{recipe.name}:{regime}",
                min_mem=int(min_mem),
            ):
                mem += 1

    repeat_rate = rep_sum / float(rep_count) if rep_count > 0 else 0.0
    legacy_reward = compute_reward(q14, q15, best, regime, repeat_rate, reward_q15, reward_q14)

    hub.learn_with_feedback(context, c15[:10], result_n1)
    hub.learn_with_feedback(context, c18[:10], result_n1)

    return {
        "reward": float(legacy_reward),
        "legacy_reward": float(legacy_reward),
        "q14": int(q14),
        "q15": int(q15),
        "melhor_acerto": int(best),
        "active": int(brains_ativos),
        "mem": int(mem),
        "regime": regime,
        "repeat_rate": float(repeat_rate),
        "hits_distribution": hits_distribution,
        "evaluated_games": evaluated_games,
    }


def record_smart_step(
    conn: sqlite3.Connection,
    run_id: int,
    concurso_n: int,
    arm: SmartArm,
    recipe: SmartRecipe,
    result: Dict[str, Any],
    totals: Dict[str, int],
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_smart_steps(
            run_id, concurso_n, concurso_n1, arm_name, recipe_name, regime, brains_ativos, reward,
            melhor_acerto, q14, q15, detalhes_json, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(run_id),
            int(concurso_n),
            int(concurso_n + 1),
            arm.name,
            recipe.name,
            str(result.get("regime", "neutro")),
            int(result["active"]),
            float(result["reward"]),
            int(result["melhor_acerto"]),
            int(result["q14"]),
            int(result["q15"]),
            json.dumps(totals, ensure_ascii=False),
            now_str(),
        ),
    )
    conn.execute(
        """
        INSERT INTO backtest_smart_recipe_trials(
            run_id, recipe_name, concurso_n, reward, q14, q15, best_hit, regime, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(run_id),
            recipe.name,
            int(concurso_n),
            float(result["reward"]),
            int(result["q14"]),
            int(result["q15"]),
            int(result["melhor_acerto"]),
            str(result.get("regime", "neutro")),
            now_str(),
        ),
    )
    conn.commit()


def build_default_arms() -> List[SmartArm]:
    return [
        SmartArm("smart_conservador", janela=180, top_n=120, base_per_brain=60, boost_top_brains=10),
        SmartArm("smart_balanceado", janela=280, top_n=180, base_per_brain=80, boost_top_brains=20),
        SmartArm("smart_agressivo", janela=380, top_n=250, base_per_brain=100, boost_top_brains=30),
        SmartArm("smart_recente_forte", janela=120, top_n=180, base_per_brain=90, boost_top_brains=35),
        SmartArm("smart_consenso", janela=300, top_n=220, base_per_brain=75, boost_top_brains=25),
    ]


def log_smart_summary(
    done: int,
    totals: Dict[str, int],
    arm_stats: Dict[str, ArmStats],
    recipe_stats: Dict[str, RecipeStats],
    recipes: Dict[str, SmartRecipe],
    run_id: int,
    run_name: str,
) -> None:
    best_arm = max(arm_stats.items(), key=lambda kv: kv[1].mean_reward) if arm_stats else ("-", ArmStats())
    best_recipe = max(recipe_stats.items(), key=lambda kv: kv[1].mean_reward) if recipe_stats else ("-", RecipeStats())
    best_recipe_name = best_recipe[0]
    best_recipe_status = recipes.get(best_recipe_name, SmartRecipe("-", members=[])).status

    log("=========================================")
    log("📊 RESUMO PARCIAL — BACKTEST SMART")
    log("=========================================")
    log(f"📌 run_id={run_id} | run_name={run_name}")
    log(f"🔢 steps={done}")
    log(f"🔥 total_14+={totals['q14']} | 🏆 total_15={totals['q15']} | 💾 memoria+={totals['mem']}")
    log(f"🧠 best_arm={best_arm[0]} | reward_médio={best_arm[1].mean_reward:.3f} | melhor_hit={best_arm[1].best_hit}")
    log(
        f"🧬 best_recipe={best_recipe_name}({best_recipe_status}) | "
        f"reward_médio={best_recipe[1].mean_reward:.3f} | melhor_hit={best_recipe[1].best_hit}"
    )
    log("✅ Treino continua automaticamente...")
    log("=========================================")






def _ensure_user_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS generated_batches (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          run_id INTEGER,
          created_at TEXT,
          concurso_alvo INTEGER,
          mode TEXT,
          tipo_jogo INTEGER,
          fechamento_tipo TEXT,
          pool_size INTEGER,
          max_jogos INTEGER,
          arm TEXT,
          recipe TEXT,
          brains_signature TEXT,
          exploration_rate REAL,
          seed INTEGER,
          status TEXT DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS idx_batches_alvo_status ON generated_batches(concurso_alvo, status);

        CREATE TABLE IF NOT EXISTS generated_games (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_id INTEGER,
          dezenas_json TEXT,
          score_internal REAL,
          rank INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_games_batch ON generated_games(batch_id);

        CREATE TABLE IF NOT EXISTS batch_results (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          batch_id INTEGER,
          concurso_num INTEGER,
          checked_at TEXT,
          hit_max INTEGER,
          hits_json TEXT,
          best_game_id INTEGER
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_batch_results_batch ON batch_results(batch_id);
        """
    )
    conn.commit()

def _bootstrap_database_if_missing_base() -> None:
    """Garante schema/base mínima quando o DB está vazio ou sem tabela concursos."""
    probe = get_conn()
    try:
        if safe_table_exists(probe, "concursos"):
            return
    finally:
        probe.close()

    log("[AUTO] Tabela 'concursos' ausente. Executando START/startBD.py automaticamente...")
    cmd = [sys.executable, str(ROOT / "START" / "startBD.py")]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err_tail = (proc.stderr or proc.stdout or "").strip()[-1200:]
        raise RuntimeError(
            "Falha na criação automática do banco via START/startBD.py. "
            "Execute manualmente 'python START/startBD.py'.\n" + err_tail
        )


def ensure_runtime_tables(conn: sqlite3.Connection) -> None:
    """Cria tabelas de runtime opcionais para evitar falhas por schema parcial."""
    ensure_smart_tables(conn)
    ensure_meta_tables(conn)
    ensure_memory_tables(conn)
    _ensure_user_tables(conn)

def main() -> None:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Backtest inteligente separado (N->N+1), focado em 14/15.")
    parser.add_argument("--steps", type=int, default=120, help="Quantidade de concursos para processar (0=infinito).")
    parser.add_argument("--minutes", type=int, default=0, help="Parada por tempo em minutos.")
    parser.add_argument("--save-every", type=int, default=10, help="Salvar estado dos cérebros a cada N steps.")
    parser.add_argument("--progress-every", type=int, default=5, help="Exibir progresso a cada N steps.")
    parser.add_argument("--summary-every", type=int, default=0, help="Exibir resumo parcial completo a cada N steps (0=desliga).")
    parser.add_argument("--avaliar-top-k", type=int, default=40, help="Quantos candidatos avaliar para 15 e 18.")
    parser.add_argument("--recent-window", type=int, default=220, help="Janela recente para score temporal dos cérebros.")
    parser.add_argument("--ucb-c", type=float, default=1.25, help="Força de exploração UCB dos arms.")
    parser.add_argument("--recipe-ucb-c", type=float, default=1.10, help="Força de exploração UCB das receitas.")
    parser.add_argument("--recipe-evolve-every", type=int, default=15, help="Cria receita filha a cada N steps.")
    parser.add_argument("--recipe-max-members", type=int, default=22, help="Máximo de cérebros por receita auto.")
    parser.add_argument("--recipe-promote-reward", type=float, default=2.8, help="Média mínima para promover receita.")
    parser.add_argument("--recipe-min-pulls", type=int, default=8, help="Mínimo de testes antes de promover/parkear.")
    parser.add_argument("--revive-parked-every", type=int, default=30, help="Tenta reviver receitas parked a cada N steps.")
    parser.add_argument("--reward-q15", type=float, default=5.0, help="Peso do acerto 15 na recompensa.")
    parser.add_argument("--reward-q14", type=float, default=1.5, help="Peso do acerto 14 na recompensa.")
    parser.add_argument("--min-mem", type=int, default=12, help="Mínimo de acertos para ir à memória forte.")
    parser.add_argument("--run-name", type=str, default="smart_backtest", help="Nome lógico da rodada.")
    parser.add_argument("--seed", type=int, default=None, help="Seed opcional para reprodutibilidade.")
    parser.add_argument("--heartbeat-seconds", type=int, default=15, help="Intervalo do heartbeat para evitar tela sem logs.")
    parser.add_argument("--profile-steps", type=int, default=0, help="Se 1, imprime tempo por fase em cada resumo de progresso.")
    args = parser.parse_args()

    progress = ProgressPrinter(
        progress_every_steps=int(args.progress_every),
        heartbeat_seconds=int(args.heartbeat_seconds),
        profile_steps=bool(int(args.profile_steps)),
    )
    step_timer = StepTimer()
    heartbeat = Heartbeat(progress, seconds=int(args.heartbeat_seconds), freeze_warn_seconds=max(60, int(args.heartbeat_seconds) * 4))
    heartbeat.start()

    meta_config = load_json_config(ROOT / "config" / "meta_controller.json", {"enabled": False})
    diversity_cfg = load_json_config(ROOT / "config" / "diversity.json", {"enabled": False})
    reward_v2_cfg = load_json_config(ROOT / "config" / "reward_v2.json", {"enabled": False})
    regime_cfg = load_json_config(ROOT / "config" / "regime_detector.json", {"enabled": False})
    stagnation_cfg = load_json_config(ROOT / "config" / "stagnation.json", {"enabled": False})
    mode_cfg = load_json_config(ROOT / "config" / "production_research.json", {"enabled": False})
    portfolio_cfg = load_json_config(ROOT / "config" / "portfolio.json", {"enabled": False})
    ab_cfg = load_json_config(ROOT / "config" / "ab_testing.json", {"enabled": False})
    checkpoint_cfg = load_json_config(ROOT / "config" / "checkpoint.json", {"enabled": False})
    memory_refiner_cfg = load_json_config(ROOT / "config" / "memory_refiner.json", {"enabled": False})
    baseline_cfg = load_json_config(ROOT / "config" / "baseline.json", {"enabled": False})
    validator_cfg = load_json_config(ROOT / "config" / "validator.json", {"enabled": False})
    reporting_cfg = load_json_config(ROOT / "config" / "reporting.json", {"enabled": False})
    performance_cfg = load_json_config(ROOT / "config" / "performance.json", {"profile": "low_cpu"})
    auto_tuning_cfg = load_json_config(ROOT / "config" / "auto_tuning.json", {"enabled": False})
    learning_monitor_cfg = load_json_config(ROOT / "config" / "learning_monitor.json", {"enabled": False})

    seed = int(args.seed) if args.seed is not None else random.SystemRandom().randint(1, 2_147_483_647)
    random.seed(seed)
    np.random.seed(seed)

    _bootstrap_database_if_missing_base()
    conn = get_conn()
    run_id = None
    meta_run_id = None
    try:
        if not safe_table_exists(conn, "concursos"):
            raise RuntimeError("Tabela 'concursos' ainda não existe após bootstrap automático.")

        ensure_runtime_tables(conn)
        if bool(performance_cfg.get("sqlite_optimize", True)):
            apply_sqlite_pragmas(conn, str(performance_cfg.get("profile", "low_cpu")))
        ensure_indexes(conn)
        checkpoint_manager = CheckpointManager(conn, checkpoint_cfg)
        memory_refiner = MemoryRefiner(conn, memory_refiner_cfg)
        strategy_validator = StrategyValidator(conn, validator_cfg, baseline_cfg)
        telemetry_writer = TelemetryWriter(conn, reporting_cfg)
        feature_cache = FeatureCache(conn, performance_cfg)
        throttle = Throttle(performance_cfg)
        auto_tuner = AutoTuner(conn, auto_tuning_cfg, str(ROOT / "config"))

        resume_last = bool(checkpoint_cfg.get("enabled", False)) and bool(checkpoint_cfg.get("resume_last_run", True))
        resume_state = None
        if resume_last:
            open_smart = _latest_open_run_id(conn, "backtest_smart_runs", "id", "finished_at IS NULL")
            open_meta = _latest_open_run_id(conn, "runs", "id", "status='running'")
            if open_smart is not None and open_meta is not None:
                run_id = int(open_smart)
                meta_run_id = int(open_meta)
                resume_state = checkpoint_manager.load_latest_valid(int(meta_run_id))

        if run_id is None:
            run_id = start_smart_run(conn, args.run_name)
        if meta_run_id is None:
            meta_run_id = start_meta_run(conn, "backtest_smart", {"args": vars(args), "meta": meta_config}, seed)

        concursos = fetch_all_concursos(conn)
        if len(concursos) < 2:
            raise RuntimeError("Poucos concursos para N->N+1.")

        last_trainable = concursos[-2]
        ck = get_smart_checkpoint(conn)
        trainable = [c for c in concursos if c <= last_trainable]
        pos = trainable.index(ck) + 1 if ck in trainable else 0

        hub = BrainHub(conn)
        loaded = register_brains_auto(conn, hub)
        if not loaded:
            raise RuntimeError("Nenhum cérebro carregado.")
        hub.load_all()

        recipes = ensure_seed_recipes(conn, loaded)
        recipe_stats = {name: RecipeStats() for name in recipes.keys()}
        arms = build_default_arms()
        arm_stats = {a.name: ArmStats() for a in arms}
        meta_enabled = bool(meta_config.get("enabled", False))
        meta_controller = MetaController(meta_config, model_store=ModelStore()) if meta_enabled else None
        stagnation_tracker = StagnationTracker(stagnation_cfg)
        mode_manager = ModeManager(mode_cfg)
        portfolio_builder = PortfolioBuilder(portfolio_cfg)
        ab_manager = ABTestingManager(ab_cfg)
        promotion_manager = PromotionManager(ab_cfg)
        learning_monitor = LearningMonitor(learning_monitor_cfg)
        learning_snapshot: Dict[str, Any] = {"status": "warmup", "policy": learning_monitor.policy.to_dict()}
        reward_history: List[float] = []
        last_mode = "production"
        last_decision_policy = {"arm": "", "recipe": "", "exploration_rate": 0.5, "brain_mask": []}
        last_diversity = 0.0
        last_hits_distribution = {"12": 0, "13": 0, "14": 0, "15": 0}

        start = time.time()
        done = 0
        totals = {"q14": 0, "q15": 0, "mem": 0}

        log("=========================================")
        log("🧠 BACKTEST SMART AUTÔNOMO — FOCO 14/15")
        log("=========================================")
        log(f"📌 run_id={run_id} | run_name={args.run_name}")
        log(f"📌 cérebros carregados={len(loaded)} | receitas={len(recipes)}")

        config_hash = compute_config_hash(str(ROOT / "config"))
        artifacts = {
            "config_hash": config_hash,
            "meta_controller_enabled": str(bool(meta_config.get("enabled", False))),
            "reward_v2_enabled": str(bool(reward_v2_cfg.get("enabled", False))),
            "mode_manager_enabled": str(bool(mode_cfg.get("enabled", False))),
            "portfolio_enabled": str(bool(portfolio_cfg.get("enabled", False))),
            "memory_refiner_enabled": str(bool(memory_refiner_cfg.get("enabled", False))),
            "git_commit": try_get_git_commit(),
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "seed": str(seed),
            "learning_monitor_enabled": str(bool(learning_monitor_cfg.get("enabled", False))),
        }
        if bool(reporting_cfg.get("enabled", True)) and meta_run_id is not None:
            for k, v in artifacts.items():
                telemetry_writer.log_run_artifact(int(meta_run_id), k, v)

        if resume_state:
            try:
                random.setstate(_decode_obj(str(resume_state.get("rng_state_py", ""))))
            except Exception:
                pass
            try:
                np.random.set_state(_decode_obj(str(resume_state.get("rng_state_np", ""))))
            except Exception:
                pass
            if meta_controller is not None:
                meta_controller.set_state(dict(resume_state.get("meta_controller", {})))
            mode_manager.set_state(dict(resume_state.get("mode_manager", {})))
            stagnation_tracker.set_state(dict(resume_state.get("stagnation", {})))
            ab_manager.set_state(dict(resume_state.get("ab_testing", {})))
            learning_monitor.set_state(dict(resume_state.get("learning_monitor", {})))
            reward_history = list(resume_state.get("reward_history", reward_history))
            done = int(resume_state.get("step", done))
            last_mode = str(resume_state.get("mode", last_mode))
            last_decision_policy = dict(resume_state.get("policy", last_decision_policy))
            last_diversity = float(resume_state.get("last_diversity", last_diversity))
            last_hits_distribution = dict(resume_state.get("last_hits_distribution", last_hits_distribution))
            restored_ref = int(resume_state.get("concurso_ref", 0))
            if restored_ref in trainable:
                pos = (trainable.index(restored_ref) + 1) % max(1, len(trainable))
            _restore_brain_mask(hub, resume_state.get("policy", {}).get("brain_mask", []))
            learning_snapshot = dict(resume_state.get("learning_snapshot", learning_snapshot))
            log(f"♻️ Auto-resume aplicado no step={done} concurso_ref={restored_ref}")

        while True:
            if args.steps > 0 and done >= int(args.steps):
                break
            if args.minutes > 0 and (time.time() - start) >= float(args.minutes) * 60.0:
                break

            throttle.maybe_sleep(done + 1)

            if pos >= len(trainable):
                pos = 0
            concurso_n = int(trainable[pos])
            pos += 1

            step_timer.start_step()
            progress.set_state(step=int(done + 1), concurso=concurso_n, phase="features")

            context_probe = build_context(conn, concurso_n, 80)
            regime = detect_regime(context_probe)
            phase_scores = fetch_brain_phase_scores(conn, int(args.recent_window))

            arm_default = choose_arm_ucb(arms, arm_stats, total_steps=max(1, done + 1), c=float(args.ucb_c), regime=regime)
            recipe_default = choose_recipe_ucb(recipes, recipe_stats, total_steps=max(1, done + 1), c=float(args.recipe_ucb_c))

            stag_state_pre = stagnation_tracker.peek()
            baseline_n_perf = min(20, len(reward_history))
            baseline_perf = (sum(reward_history[-baseline_n_perf:]) / float(baseline_n_perf)) if baseline_n_perf > 0 else 0.0
            recent_perf = {
                "step": int(done + 1),
                "is_bad": baseline_n_perf >= 8 and baseline_perf < 0.0,
                "is_stable": baseline_n_perf >= 8 and abs(baseline_perf) < 0.25,
            }
            prev_mode = str(last_mode)
            mode = mode_manager.decide_mode(regime_id=0, stagnation=stag_state_pre, recent_perf=recent_perf)
            features = feature_cache.get_features(
                concurso_n,
                overrides={"stagnation_score": float(stag_state_pre.get("stagnation_score", 0.0))},
            )
            regime_id = detect_regime_v2(features, regime_cfg)
            features["regime_id"] = float(max(0.0, min(1.0, regime_id / 3.0)))
            mode = mode_manager.decide_mode(regime_id=regime_id, stagnation=stag_state_pre, recent_perf=recent_perf)
            valid_recipes = [k for k, v in recipes.items() if v.status in {"seed", "candidate", "promoted", "parked"}]
            slots = ab_manager.choose_slots(
                mode=mode,
                available_arms=[a.name for a in arms],
                available_recipes=valid_recipes,
                available_brains=loaded,
                core_brains=list(mode_cfg.get("core_brains", [])),
            )
            decision = {
                "arm": arm_default.name,
                "recipe": recipe_default.name,
                "exploration_rate": 0.5,
                "confidence": 1.0,
                "fallback_used": 0,
                "explore_level": "medio",
            }
            if meta_controller is not None:
                decision = meta_controller.decide(
                    features=features,
                    arms=[a.name for a in arms],
                    recipes=valid_recipes,
                    default_arm=arm_default.name,
                    default_recipe=recipe_default.name,
                    regime_unstable=(regime_id == 3),
                )
            if mode == "research":
                if slots.get("candidate_arms"):
                    decision["arm"] = str(slots["candidate_arms"][0])
                if slots.get("candidate_recipes"):
                    decision["recipe"] = str(slots["candidate_recipes"][0])

            monitor_policy = dict(learning_snapshot.get("policy", {}))
            if bool(stag_state_pre.get("rescue_mode", False)) or bool(monitor_policy.get("rescue_mode", False)):
                decision["exploration_rate"] = min(
                    1.0,
                    float(decision.get("exploration_rate", 0.5)) + float(stagnation_cfg.get("rescue_exploration_boost", 0.10)),
                )

            decision["exploration_rate"] = max(
                0.0,
                min(1.0, float(decision.get("exploration_rate", 0.5)) + float(monitor_policy.get("exploration_delta", 0.0))),
            )
            decision["confidence"] = max(
                0.0,
                min(1.0, float(decision.get("confidence", 0.0)) * float(monitor_policy.get("confidence_mult", 1.0))),
            )
            if str(monitor_policy.get("force_mode", "")).strip() == "research":
                mode = "research"

            arm_map = {a.name: a for a in arms}
            arm = arm_map.get(str(decision["arm"]), arm_default)
            recipe = recipes.get(str(decision["recipe"]), recipe_default)
            last_mode = mode
            last_decision_policy = {
                "arm": arm.name,
                "recipe": recipe.name,
                "exploration_rate": float(decision.get("exploration_rate", 0.5)),
                "brain_mask": _current_brain_mask(hub),
            }

            if meta_run_id is not None:
                conn.execute(
                    """
                    INSERT INTO context_snapshots(run_id, step, concurso_ref, features_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(meta_run_id), int(done + 1), int(concurso_n), json.dumps(features, ensure_ascii=False), now_str()),
                )
                conn.execute(
                    """
                    INSERT INTO decisions(run_id, step, arm, recipe, exploration_rate, confidence, fallback_used, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(meta_run_id),
                        int(done + 1),
                        arm.name,
                        recipe.name,
                        float(decision.get("exploration_rate", 0.5)),
                        float(decision.get("confidence", 0.0)),
                        int(decision.get("fallback_used", 0)),
                        now_str(),
                    ),
                )
                conn.commit()

            step_timer.mark("features")
            progress.set_state(phase="generate_candidates", mode=mode, regime=regime, arm=arm.name, recipe=recipe.name)
            result = run_step(
                conn=conn,
                hub=hub,
                concurso_n=concurso_n,
                arm=arm,
                recipe=recipe,
                recent_window=int(args.recent_window),
                avaliar_top_k=int(args.avaliar_top_k),
                min_mem=int(args.min_mem),
                reward_q15=float(args.reward_q15),
                reward_q14=float(args.reward_q14),
                mode=mode,
                portfolio_builder=portfolio_builder,
                portfolio_cfg=portfolio_cfg,
                forced_brains=list(mode_cfg.get("core_brains", [])) if mode == "production" else [],
                experimental_brains=slots.get("candidate_brains", []),
                memory_refiner_cfg=memory_refiner_cfg,
            )
            step_timer.mark("generate_candidates")
            progress.set_state(phase="evaluate_hits")

            a = arm_stats[arm.name]
            a.pulls += 1
            a.reward_sum += float(result["reward"])
            a.best_hit = max(a.best_hit, int(result["melhor_acerto"]))

            rs = recipe_stats.setdefault(recipe.name, RecipeStats())
            rs.pulls += 1
            rs.reward_sum += float(result["reward"])
            rs.q14_sum += int(result["q14"])
            rs.q15_sum += int(result["q15"])
            rs.best_hit = max(rs.best_hit, int(result["melhor_acerto"]))

            totals["q14"] += int(result["q14"])
            totals["q15"] += int(result["q15"])
            totals["mem"] += int(result["mem"])
            done += 1

            diversity = portfolio_diversity(
                result.get("evaluated_games", []),
                pair_sample_max=int(diversity_cfg.get("pair_sample_max", 200)),
            ) if bool(diversity_cfg.get("enabled", True)) else max(0.0, min(1.0, 1.0 - float(result.get("repeat_rate", 0.0))))
            step_timer.mark("build_portfolio")

            baseline_n = min(20, len(reward_history))
            baseline = (sum(reward_history[-baseline_n:]) / float(baseline_n)) if baseline_n > 0 else float(result.get("legacy_reward", 0.0))
            stag_state = stagnation_tracker.update(
                hit_max=int(result["melhor_acerto"]),
                reward=float(result.get("legacy_reward", result["reward"])),
                arm=arm.name,
                recipe=recipe.name,
            )
            features["stagnation_score"] = float(stag_state.get("stagnation_score", 0.0))

            if bool(reward_v2_cfg.get("enabled", False)):
                result["reward"] = compute_reward_v2(
                    hit_max=int(result["melhor_acerto"]),
                    hits_distribution=result.get("hits_distribution", {}),
                    diversity=float(diversity),
                    context={
                        "legacy_reward": float(result.get("legacy_reward", 0.0)),
                        "recent_reward_baseline": float(baseline),
                        "diversity_cfg": diversity_cfg,
                        "rescue_penalty_after": 8,
                    },
                    decision=decision,
                    stagnation=stag_state,
                    cfg=reward_v2_cfg,
                )

            reward_history.append(float(result["reward"]))
            learning_snapshot = learning_monitor.update(
                step=int(done),
                hit_max=int(result["melhor_acerto"]),
                reward=float(result["reward"]),
                mode=str(mode),
            )
            if bool(learning_snapshot.get("should_log", False)):
                trend = dict(learning_snapshot.get("trend", {}))
                base = dict(learning_snapshot.get("baseline", {}))
                log(
                    f"{_status_icon(str(learning_snapshot.get('status', 'warmup')))} STATUS: "
                    f"{_status_label(str(learning_snapshot.get('status', 'warmup')))} | "
                    f"Δ14+={float(base.get('delta_q14_vs_baseline', 0.0))*100:+.2f}% | "
                    f"reward={float(learning_snapshot.get('metrics_main', {}).get('reward_mean', 0.0)):+.3f} | "
                    f"tend={float(trend.get('delta_reward', 0.0)):+.3f}"
                )
                if str(learning_snapshot.get("policy", {}).get("force_mode", "")) == "research":
                    log("→ Mudando para modo PESQUISA (learning monitor)")
            step_timer.mark("evaluate_hits")
            last_diversity = float(diversity)
            last_hits_distribution = dict(result.get("hits_distribution", {}))

            ab_key = f"{mode}:{arm.name}:{recipe.name}"
            ab_manager.update_result(ab_key, float(result["reward"]), int(result["melhor_acerto"]))
            ab_manager.record_experiment(
                {
                    "step": int(done),
                    "mode": mode,
                    "arm": arm.name,
                    "recipe": recipe.name,
                    "slots": slots,
                    "reward": float(result["reward"]),
                    "hit_max": int(result["melhor_acerto"]),
                }
            )

            cand_stats = {
                "n": int(ab_manager.stats.get(ab_key, {}).get("n", 0)),
                "mean_reward": float(ab_manager.stats.get(ab_key, {}).get("reward_sum", 0.0)) / max(1, int(ab_manager.stats.get(ab_key, {}).get("n", 0))),
                "hit_max": int(ab_manager.stats.get(ab_key, {}).get("hit_max", 0)),
            }
            base_stats = {
                "mean_reward": baseline,
                "hit_max": max((x.best_hit for x in arm_stats.values()), default=0),
            }

            validator_report = {
                "passes_baseline": False,
                "passes_validation": False,
                "candidate_score_mean": 0.0,
                "baseline_global_mean": 0.0,
                "baseline_recent_mean": 0.0,
            }
            if cand_stats["n"] >= 8 and bool(validator_cfg.get("enabled", False)):
                def _candidate_callable(concurso_ref: int, tipo_jogo: int, max_games: int, context: dict):
                    ctx = build_context(conn, int(concurso_ref), arm.janela)
                    pm = build_per_brain_map(loaded, phase_scores, arm.base_per_brain, arm.boost_top_brains, recipe.boosts)
                    g = hub.generate_games(context=ctx, size=int(tipo_jogo), per_brain=pm, top_n=min(120, int(max_games) * 3)) or []
                    out = []
                    for item in g[: int(max_games)]:
                        jogo = sorted(set(int(x) for x in item.get("jogo", []) if x is not None))
                        if len(jogo) == int(tipo_jogo):
                            out.append(jogo)
                    return out

                validator_report = strategy_validator.validate_candidate(
                    candidate_callable=_candidate_callable,
                    concurso_ref=int(concurso_n),
                    tipo_jogo=15,
                    max_games=min(int(baseline_cfg.get("max_games", 60)), 60),
                    context={"arm": arm.name, "recipe": recipe.name, "mode": mode},
                )

                if bool(reporting_cfg.get("enabled", True)) and meta_run_id is not None:
                    telemetry_writer.log_experiment(
                        {
                            "run_id": int(meta_run_id),
                            "kind": "validator",
                            "candidate_name": f"{arm.name}:{recipe.name}",
                            "baseline_name": "global+recent_120",
                            "window_steps": int(validator_cfg.get("valid_window", 120)),
                            "status": "finished",
                            "candidate_score_mean": float(validator_report.get("candidate_score_mean", 0.0)),
                            "baseline_score_mean": float(max(validator_report.get("baseline_global_mean", 0.0), validator_report.get("baseline_recent_mean", 0.0))),
                            "passes": bool(validator_report.get("passes_validation", False)),
                            "notes": str(validator_report.get("reason", "")),
                        }
                    )

                if validator_report.get("passes_validation") and bool(memory_refiner_cfg.get("enabled", False)):
                    conn.execute(
                        """
                        UPDATE memoria_jogos_gold
                        SET validated=1
                        WHERE strategy_signature LIKE ?
                        """,
                        (f"%{recipe.name}%",),
                    )
                    conn.commit()

            promo_action = promotion_manager.evaluate_candidate({**cand_stats, **validator_report}, base_stats)
            if promo_action in {"park", "disable"} and recipe.name in recipes:
                recipes[recipe.name].status = "parked" if promo_action == "park" else "parked"
            elif promo_action == "promote" and recipe.name in recipes:
                recipes[recipe.name].status = "promoted"

            if meta_controller is not None:
                meta_controller.train_step(features, decision, float(result["reward"]), regime_unstable=(regime_id == 3))

            if meta_run_id is not None:
                conn.execute(
                    """
                    INSERT INTO outcomes(run_id, step, concurso_ref, hit_max, reward, diversity, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(meta_run_id),
                        int(done),
                        int(concurso_n + 1),
                        int(result["melhor_acerto"]),
                        float(result["reward"]),
                        float(diversity),
                        now_str(),
                    ),
                )
                conn.commit()

            step_timer.mark("train_meta")
            progress.set_state(phase="checkpoint")
            ck_enabled = bool(checkpoint_cfg.get("enabled", False))
            save_every = max(1, int(checkpoint_cfg.get("save_every_steps", 5)))
            mode_switched = mode != str(prev_mode)
            should_save_ck = ck_enabled and (done % save_every == 0 or mode_switched)
            if should_save_ck and meta_run_id is not None:
                if meta_controller is not None:
                    meta_controller.model_store.save_state(
                        {
                            "arm_model": meta_controller.arm_model,
                            "recipe_model": meta_controller.recipe_model,
                            "explore_model": meta_controller.explore_model,
                            "bandit": meta_controller.bandit.to_state(),
                            "arm_classes": meta_controller.arm_classes,
                            "recipe_classes": meta_controller.recipe_classes,
                            "is_trained": meta_controller.is_trained,
                        }
                    )
                ck_state = {
                    "run_id": int(meta_run_id),
                    "step": int(done),
                    "concurso_ref": int(concurso_n),
                    "rng_seed_base": int(seed),
                    "rng_state_py": _encode_obj(random.getstate()),
                    "rng_state_np": _encode_obj(np.random.get_state()),
                    "meta_controller": meta_controller.get_state() if meta_controller is not None else {},
                    "bandit": meta_controller.bandit.to_state() if meta_controller is not None else {},
                    "mode": str(mode),
                    "mode_manager": mode_manager.get_state(),
                    "stagnation": stagnation_tracker.get_state(),
                    "ab_testing": ab_manager.get_state(),
                    "policy": last_decision_policy,
                    "last_diversity": float(last_diversity),
                    "last_hits_distribution": last_hits_distribution,
                    "reward_history": reward_history[-50:],
                    "learning_monitor": learning_monitor.get_state(),
                    "learning_snapshot": learning_snapshot,
                }
                checkpoint_manager.save(ck_state)

            step_timer.mark("checkpoint")
            progress.set_state(phase="db_commit")
            if bool(memory_refiner_cfg.get("enabled", False)) and done % max(1, int(memory_refiner_cfg.get("batch_size", 2000) // 400)) == 0:
                try:
                    memory_refiner.run_batch(batch_size=int(memory_refiner_cfg.get("batch_size", 2000)))
                except Exception:
                    pass

            recipes[recipe.name] = update_recipe_status(
                recipe=recipes[recipe.name],
                stats=rs,
                min_pulls=int(args.recipe_min_pulls),
                promote_reward=float(args.recipe_promote_reward),
            )
            upsert_recipe(conn, recipes[recipe.name])

            if recipes[recipe.name].status == "promoted":
                register_hypothesis(
                    conn,
                    run_id=run_id,
                    kind="recipe",
                    title=f"promoted:{recipe.name}",
                    payload={"members": recipes[recipe.name].members, "boosts": recipes[recipe.name].boosts},
                    status="promoted",
                    score=rs.mean_reward,
                )

            if int(args.recipe_evolve_every) > 0 and done % int(args.recipe_evolve_every) == 0:
                child = evolve_recipe(recipes, recipe_stats, loaded, phase_scores, done, int(args.recipe_max_members))
                if child.name not in recipes:
                    recipes[child.name] = child
                    recipe_stats[child.name] = RecipeStats()
                    upsert_recipe(conn, child)
                    register_hypothesis(
                        conn,
                        run_id=run_id,
                        kind="recipe",
                        title=f"created:{child.name}",
                        payload={"parents": "auto", "members": child.members, "boosts": child.boosts},
                        status="candidate",
                        score=0.0,
                    )
                    log(f"🧬 Nova receita criada automaticamente: {child.name} | membros={len(child.members)}")

            if int(args.revive_parked_every) > 0 and done % int(args.revive_parked_every) == 0:
                revived = revive_parked_recipes(recipes, recipe_stats, phase_scores, limit=2)
                for name in revived:
                    upsert_recipe(conn, recipes[name])
                    register_hypothesis(
                        conn,
                        run_id=run_id,
                        kind="revive",
                        title=f"revived:{name}",
                        payload={"reason": "phase_score_shift"},
                        status="candidate",
                        score=recipe_stats.get(name, RecipeStats()).mean_reward,
                    )

            record_smart_step(
                conn=conn,
                run_id=int(run_id),
                concurso_n=concurso_n,
                arm=arm,
                recipe=recipe,
                result=result,
                totals={"total_q14": totals["q14"], "total_q15": totals["q15"], "total_mem": totals["mem"]},
            )
            set_smart_checkpoint(conn, concurso_n)

            if done % max(1, int(args.save_every)) == 0:
                hub.save_all()

            step_timer.mark("db_commit")
            phases = step_timer.end_step()
            progress.set_state(phase="idle")
            if done == 1 or done % max(1, int(args.progress_every)) == 0:
                best_arm = max(arm_stats.items(), key=lambda kv: kv[1].mean_reward)
                best_recipe = max(recipe_stats.items(), key=lambda kv: kv[1].mean_reward)
                progress.log_step(
                    {
                        "step": done,
                        "N_from": concurso_n,
                        "N_to": concurso_n + 1,
                        "regime": result.get("regime", "neutro"),
                        "mode": mode,
                        "arm": arm.name,
                        "recipe": f"{recipe.name}({recipes[recipe.name].status})",
                        "reward": result["reward"],
                        "hit_max": result["melhor_acerto"],
                        "total_14p": totals["q14"],
                        "total_15": totals["q15"],
                        "best_arm": f"{best_arm[0]}({best_arm[1].mean_reward:.2f})",
                        "best_recipe": f"{best_recipe[0]}({best_recipe[1].mean_reward:.2f})",
                        "elapsed_step_s": phases.get("total", 0.0),
                    }
                )
                if bool(int(args.profile_steps)):
                    progress.log_phases(phases)

            rep_every = max(1, int(reporting_cfg.get("summary_every_steps", 200)))
            if bool(reporting_cfg.get("enabled", True)) and meta_run_id is not None and done % rep_every == 0:
                telemetry_writer.log_summary_step(
                    int(meta_run_id),
                    int(done),
                    {
                        "mode": mode,
                        "arm": arm.name,
                        "recipe": recipe.name,
                        "reward": float(result.get("reward", 0.0)),
                        "hit_max": int(result.get("melhor_acerto", 0)),
                        "diversity": float(diversity),
                        "fallback_used": int(decision.get("fallback_used", 0)),
                        "rescue_mode": bool(stag_state.get("rescue_mode", False)),
                        "learning_monitor": {
                            "status": str(learning_snapshot.get("status", "warmup")),
                            "trend": dict(learning_snapshot.get("trend", {})),
                            "baseline": dict(learning_snapshot.get("baseline", {})),
                            "policy": dict(learning_snapshot.get("policy", {})),
                            "metrics_main": dict(learning_snapshot.get("metrics_main", {})),
                        },
                    },
                )

            if bool(auto_tuning_cfg.get("enabled", False)):
                auto_tuner.run_if_due(int(meta_run_id) if meta_run_id is not None else int(run_id), int(done))

            if int(args.summary_every) > 0 and done % int(args.summary_every) == 0:
                log_smart_summary(
                    done=done,
                    totals=totals,
                    arm_stats=arm_stats,
                    recipe_stats=recipe_stats,
                    recipes=recipes,
                    run_id=int(run_id),
                    run_name=str(args.run_name),
                )

        hub.save_all()
        if bool(reporting_cfg.get("enabled", True)) and bool(reporting_cfg.get("html_enabled", True)) and meta_run_id is not None:
            try:
                generate_html_report(conn, int(meta_run_id), ROOT / "reports" / f"run_{int(meta_run_id)}.html", top_n=int(reporting_cfg.get("top_n", 10)))
            except Exception:
                pass
        log("=========================================")
        log(f"✅ Finalizado | steps={done} | total_14+={totals['q14']} | total_15={totals['q15']} | memoria+={totals['mem']}")
        log(f"📚 Receitas aprendidas no banco: {len(recipes)}")
        log("=========================================")
    finally:
        try:
            heartbeat.stop()
        except Exception:
            pass
        try:
            if run_id is not None:
                finish_smart_run(conn, int(run_id))
            if meta_run_id is not None:
                finish_meta_run(conn, int(meta_run_id), status="finished")
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    main()
