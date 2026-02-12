from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
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
from training.utils.comparador import contar_acertos


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}")


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
    max_row = conn.execute("SELECT MAX(concurso_n) FROM cerebro_performance").fetchone()
    max_n = int(max_row[0]) if max_row and max_row[0] is not None else 0
    min_n = max(1, max_n - int(recent_window) + 1)
    rows = conn.execute(
        """
        SELECT brain_id,
               SUM(CASE WHEN acertos >= 15 THEN 1 ELSE 0 END) AS q15,
               SUM(CASE WHEN acertos >= 14 THEN 1 ELSE 0 END) AS q14,
               COUNT(*) AS jogos
          FROM cerebro_performance
         WHERE concurso_n >= ?
         GROUP BY brain_id
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
) -> Dict[str, Any]:
    result_n1 = fetch_result(conn, concurso_n + 1)
    if not result_n1:
        return {"reward": 0.0, "q14": 0, "q15": 0, "melhor_acerto": 0, "active": 0, "regime": "neutro", "repeat_rate": 0.0}

    context = build_context(conn, concurso_n, arm.janela)
    regime = detect_regime(context)
    ultimo = set(context.get("ultimo_resultado", []))
    phase_scores = fetch_brain_phase_scores(conn, recent_window=recent_window)
    loaded_ids = [str(getattr(b, "id", "unknown")) for b in getattr(hub, "brains", [])]

    active_ids = _recipe_active_members(recipe, loaded_ids, phase_scores)
    brains_ativos = _set_enabled_brains(hub, active_ids)
    per_brain_map = build_per_brain_map(active_ids, phase_scores, arm.base_per_brain, arm.boost_top_brains, recipe.boosts)

    t0 = time.time()
    c15 = hub.generate_games(context=context, size=15, per_brain=per_brain_map, top_n=arm.top_n)
    c18 = hub.generate_games(context=context, size=18, per_brain=per_brain_map, top_n=arm.top_n)
    dt = time.time() - t0

    c15 = (c15 or [])[: int(avaliar_top_k)]
    c18 = (c18 or [])[: int(avaliar_top_k)]

    q14 = q15 = mem = 0
    best = 0
    rep_sum = 0.0
    rep_count = 0
    tentativa = 1
    for tipo, cands in ((15, c15), (18, c18)):
        for c in cands:
            jogo = sorted(set(int(x) for x in c.get("jogo", []) if x is not None))
            if len(jogo) != tipo:
                continue
            acertos = int(contar_acertos(jogo, result_n1))
            best = max(best, acertos)
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
    reward = compute_reward(q14, q15, best, regime, repeat_rate, reward_q15, reward_q14)

    hub.learn_with_feedback(context, c15[:10], result_n1)
    hub.learn_with_feedback(context, c18[:10], result_n1)

    return {
        "reward": float(reward),
        "q14": int(q14),
        "q15": int(q15),
        "melhor_acerto": int(best),
        "active": int(brains_ativos),
        "mem": int(mem),
        "regime": regime,
        "repeat_rate": float(repeat_rate),
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


def main() -> None:
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
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(int(args.seed))

    conn = get_conn()
    run_id = None
    try:
        if not safe_table_exists(conn, "concursos"):
            raise RuntimeError("Tabela 'concursos' não existe. Rode START/startBD.py.")

        ensure_smart_tables(conn)
        run_id = start_smart_run(conn, args.run_name)

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

        start = time.time()
        done = 0
        totals = {"q14": 0, "q15": 0, "mem": 0}

        log("=========================================")
        log("🧠 BACKTEST SMART AUTÔNOMO — FOCO 14/15")
        log("=========================================")
        log(f"📌 run_id={run_id} | run_name={args.run_name}")
        log(f"📌 cérebros carregados={len(loaded)} | receitas={len(recipes)}")

        while True:
            if args.steps > 0 and done >= int(args.steps):
                break
            if args.minutes > 0 and (time.time() - start) >= float(args.minutes) * 60.0:
                break

            if pos >= len(trainable):
                pos = 0
            concurso_n = int(trainable[pos])
            pos += 1

            context_probe = build_context(conn, concurso_n, 80)
            regime = detect_regime(context_probe)
            phase_scores = fetch_brain_phase_scores(conn, int(args.recent_window))

            arm = choose_arm_ucb(arms, arm_stats, total_steps=max(1, done + 1), c=float(args.ucb_c), regime=regime)
            recipe = choose_recipe_ucb(recipes, recipe_stats, total_steps=max(1, done + 1), c=float(args.recipe_ucb_c))

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
            )

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

            if done % max(1, int(args.progress_every)) == 0:
                best_arm = max(arm_stats.items(), key=lambda kv: kv[1].mean_reward)
                best_recipe = max(recipe_stats.items(), key=lambda kv: kv[1].mean_reward)
                log(
                    " | ".join(
                        [
                            f"step={done}",
                            f"N={concurso_n}->{concurso_n + 1}",
                            f"regime={result.get('regime', 'neutro')}",
                            f"arm={arm.name}",
                            f"recipe={recipe.name}({recipes[recipe.name].status})",
                            f"reward={result['reward']:.2f}",
                            f"hit_max={result['melhor_acerto']}",
                            f"14+={totals['q14']}",
                            f"15={totals['q15']}",
                            f"best_arm={best_arm[0]}({best_arm[1].mean_reward:.2f})",
                            f"best_recipe={best_recipe[0]}({best_recipe[1].mean_reward:.2f})",
                        ]
                    )
                )

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
        log("=========================================")
        log(f"✅ Finalizado | steps={done} | total_14+={totals['q14']} | total_15={totals['q15']} | memoria+={totals['mem']}")
        log(f"📚 Receitas aprendidas no banco: {len(recipes)}")
        log("=========================================")
    finally:
        try:
            if run_id is not None:
                finish_smart_run(conn, int(run_id))
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    main()
