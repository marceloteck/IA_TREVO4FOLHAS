from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.backtest.backtest_engine import build_context, fetch_result, register_brains_auto
from training.backtest.backtest_smart_engine import build_default_arms, choose_arm_ucb, choose_recipe_ucb, ensure_seed_recipes
from training.core.brain_hub import BrainHub
from training.meta.context_features import extract_context_features
from training.meta.meta_controller import MetaController
from training.meta.model_store import ModelStore
from training.meta.portfolio_builder import PortfolioBuilder


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_user_tables(conn: sqlite3.Connection) -> None:
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


def _latest_concurso(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(concurso) FROM concursos").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _load_json(path: Path, default: dict) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return dict(default)


def generate_batch(
    conn: sqlite3.Connection,
    concurso_alvo: int | None,
    mode: str,
    tipo_jogo: int,
    pool_size: int,
    fechamento_tipo: str,
    max_jogos: int,
) -> tuple[int, Path]:
    ensure_user_tables(conn)
    target = int(concurso_alvo) if concurso_alvo else (_latest_concurso(conn) + 1)
    seed = random.randint(1, 2_147_483_647)
    random.seed(seed)

    meta_cfg = _load_json(ROOT / "config" / "meta_controller.json", {"enabled": False})
    portfolio_cfg = _load_json(ROOT / "config" / "portfolio.json", {"enabled": False})

    hub = BrainHub(conn)
    loaded = register_brains_auto(conn, hub)
    if not loaded:
        raise RuntimeError("Nenhum cérebro carregado para geração do usuário.")
    hub.load_all()

    recipes = ensure_seed_recipes(conn, loaded)
    recipe_stats = {k: type("S", (), {"pulls": 1, "mean_reward": 0.0})() for k in recipes.keys()}
    arms = build_default_arms()
    arm_stats = {a.name: type("A", (), {"pulls": 1, "mean_reward": 0.0})() for a in arms}

    concurso_ref = target - 1
    context = build_context(conn, concurso_ref, 180)
    arm = choose_arm_ucb(arms, {k: type("Obj", (), {"pulls": 1, "mean_reward": 0.0})() for k in arm_stats}, 1, 1.0, "neutro")
    recipe = choose_recipe_ucb(recipes, {k: type("Obj", (), {"pulls": 1, "mean_reward": 0.0})() for k in recipes}, 1, 1.0)

    decision = {"arm": arm.name, "recipe": recipe.name, "exploration_rate": 0.5}
    if bool(meta_cfg.get("enabled", False)):
        mc = MetaController(meta_cfg, model_store=ModelStore())
        feats = extract_context_features(conn, concurso_ref)
        decision = mc.decide(feats, [a.name for a in arms], list(recipes.keys()), arm.name, recipe.name)
        arm = next((a for a in arms if a.name == decision["arm"]), arm)
        recipe = recipes.get(decision["recipe"], recipe)

    per_brain = {bid: max(20, int(pool_size * 2)) for bid in loaded}
    candidates = hub.generate_games(context=context, size=int(tipo_jogo), per_brain=per_brain, top_n=max(80, int(max_jogos) * 4)) or []

    recs = []
    for c in candidates:
        jogo = sorted(set(int(x) for x in c.get("jogo", []) if x is not None))
        if len(jogo) != int(tipo_jogo):
            continue
        recs.append(
            {
                "dezenas": jogo,
                "score": float(c.get("score", 0.0)),
                "origem": f"user:{arm.name}:{recipe.name}:{c.get('brain_id','unknown')}",
                "features": {"even": sum(1 for d in jogo if d % 2 == 0), "sum": sum(jogo), "repeated": 0},
            }
        )

    if bool(portfolio_cfg.get("enabled", False)):
        pb = PortfolioBuilder(portfolio_cfg)
        final_games = pb.build(recs, int(max_jogos), mode=str(mode), quotas={})
    else:
        final_games = [r["dezenas"] for r in sorted(recs, key=lambda x: x["score"], reverse=True)[: int(max_jogos)]]

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO generated_batches(run_id, created_at, concurso_alvo, mode, tipo_jogo, fechamento_tipo, pool_size, max_jogos, arm, recipe, brains_signature, exploration_rate, seed, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            None,
            now_str(),
            int(target),
            str(mode),
            int(tipo_jogo),
            str(fechamento_tipo),
            int(pool_size),
            int(max_jogos),
            str(arm.name),
            str(recipe.name),
            ",".join(sorted(loaded[:12])),
            float(decision.get("exploration_rate", 0.5)),
            int(seed),
        ),
    )
    batch_id = int(cur.lastrowid)

    for i, dezenas in enumerate(final_games, start=1):
        conn.execute(
            "INSERT INTO generated_games(batch_id, dezenas_json, score_internal, rank) VALUES (?, ?, ?, ?)",
            (int(batch_id), json.dumps(dezenas, ensure_ascii=False), float(max_jogos - i), int(i)),
        )
    conn.commit()

    out = ROOT / "exports" / f"jogos_concurso_{target}_batch_{batch_id}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        f.write(f"batch_id={batch_id} concurso_alvo={target} mode={mode}\n")
        for j, dezenas in enumerate(final_games, start=1):
            f.write(f"{j:03d}: {' '.join(f'{d:02d}' for d in dezenas)}\n")

    return batch_id, out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--concurso-alvo", type=int, default=None)
    p.add_argument("--mode", type=str, default="production")
    p.add_argument("--tipo", type=int, default=None)
    p.add_argument("--pool-size", type=int, default=None)
    p.add_argument("--fechamento", type=str, default=None)
    p.add_argument("--max-jogos", type=int, default=None)
    args = p.parse_args()

    pref = _load_json(ROOT / "config" / "fechamentos_preferencias.json", {})
    tipo = int(args.tipo if args.tipo is not None else pref.get("tipo_jogo", 15))
    pool = int(args.pool_size if args.pool_size is not None else pref.get("pool_size", 18))
    fechamento = str(args.fechamento if args.fechamento is not None else pref.get("fechamento_tipo", "POOL_VARIAVEL"))
    max_jogos = int(args.max_jogos if args.max_jogos is not None else pref.get("max_jogos", 30))

    conn = get_conn()
    try:
        batch_id, out = generate_batch(conn, args.concurso_alvo, args.mode, tipo, pool, fechamento, max_jogos)
        print(f"batch_id={batch_id}")
        print(f"export={out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
