from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.backtest.backtest_engine import build_context, register_brains_auto
from training.backtest.backtest_smart_engine import (
    build_default_arms,
    choose_arm_ucb,
    choose_recipe_ucb,
    ensure_seed_recipes,
)
from training.core.brain_hub import BrainHub
from training.meta.context_features import extract_context_features
from training.meta.meta_controller import MetaController
from training.meta.model_store import ModelStore


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path, default: dict) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return dict(default)


def _safe_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (str(table_name),),
    ).fetchone()
    return row is not None


def _latest_concurso_and_last_result(conn: sqlite3.Connection) -> tuple[int, list[int]]:
    try:
        row = conn.execute(
        """
        SELECT concurso, d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        ORDER BY concurso DESC
        LIMIT 1
        """
    ).fetchone()
    except sqlite3.OperationalError as exc:
        raise RuntimeError("Não foi possível ler a tabela concursos no SQLite. Verifique o DB_PATH e se o schema foi criado.") from exc
    if not row:
        raise RuntimeError("Tabela concursos vazia: não há dados para prever o próximo concurso.")
    return int(row[0]), [int(x) for x in row[1:]]


def _build_candidate_records(
    raw_candidates: list[dict[str, Any]],
    tipo: int,
    ultimo_resultado: list[int],
    arm_name: str,
    recipe_name: str,
) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    ultimo_set = set(int(x) for x in ultimo_resultado)
    for c in raw_candidates or []:
        jogo = sorted(set(int(x) for x in c.get("jogo", []) if x is not None))
        if len(jogo) != int(tipo):
            continue
        rep = sum(1 for d in jogo if d in ultimo_set)
        recs.append(
            {
                "dezenas": jogo,
                "score": float(c.get("score", 0.0)),
                "origem": f"predict_next:{arm_name}:{recipe_name}:{c.get('brain_id', 'unknown')}",
                "features": {
                    "even": sum(1 for d in jogo if d % 2 == 0),
                    "sum": sum(jogo),
                    "repeated": int(rep),
                },
            }
        )
    return recs


def _jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return float(inter / union) if union else 0.0


def _fallback_select(candidates: list[dict[str, Any]], max_jogos: int) -> list[list[int]]:
    ordered = sorted(candidates, key=lambda x: float(x.get("score", 0.0)), reverse=True)
    selected: list[dict[str, Any]] = []

    def _accept(cand: dict[str, Any]) -> bool:
        sset = set(int(x) for x in cand.get("dezenas", []))
        for sel in selected:
            s2 = set(int(x) for x in sel.get("dezenas", []))
            if _jaccard(sset, s2) > 0.75:
                return False
        return True

    for cand in ordered:
        if len(selected) >= int(max_jogos):
            break
        if _accept(cand):
            selected.append(cand)

    even_counts = {int(c.get("features", {}).get("even", 0)) for c in selected}
    need = [7, 8]
    for paridade in need:
        if len(selected) >= int(max_jogos):
            break
        if paridade in even_counts:
            continue
        for cand in ordered:
            if int(cand.get("features", {}).get("even", -1)) != paridade:
                continue
            if _accept(cand):
                selected.append(cand)
                even_counts.add(paridade)
                break

    if len(selected) < int(max_jogos):
        used = {tuple(c.get("dezenas", [])) for c in selected}
        for cand in ordered:
            key = tuple(cand.get("dezenas", []))
            if key in used:
                continue
            selected.append(cand)
            used.add(key)
            if len(selected) >= int(max_jogos):
                break

    return [sorted(int(x) for x in c.get("dezenas", [])) for c in selected[: int(max_jogos)]]


def _suggest_pool(jogos: list[list[int]], pool_size: int | None) -> list[int] | None:
    if not pool_size:
        return None
    counter = Counter()
    for jogo in jogos:
        counter.update(int(x) for x in jogo)
    pool = [d for d, _ in counter.most_common(int(pool_size))]
    return sorted(pool)


def _persist_if_tables_exist(
    conn: sqlite3.Connection,
    concurso_alvo: int,
    tipo: int,
    pool_size: int | None,
    max_jogos: int,
    seed: int,
    arm_name: str,
    recipe_name: str,
    brains_signature: str,
    jogos: list[list[int]],
    dry_run: bool,
) -> int | None:
    if dry_run:
        return None
    if not (_safe_table_exists(conn, "generated_batches") and _safe_table_exists(conn, "generated_games")):
        return None

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO generated_batches(
            run_id, created_at, concurso_alvo, mode, tipo_jogo, fechamento_tipo,
            pool_size, max_jogos, arm, recipe, brains_signature, exploration_rate, seed, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            None,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            int(concurso_alvo),
            "production",
            int(tipo),
            "POOL_VARIAVEL",
            int(pool_size) if pool_size is not None else None,
            int(max_jogos),
            str(arm_name),
            str(recipe_name),
            str(brains_signature),
            0.5,
            int(seed),
        ),
    )
    batch_id = int(cur.lastrowid)

    for idx, jogo in enumerate(jogos, start=1):
        conn.execute(
            "INSERT INTO generated_games(batch_id, dezenas_json, score_internal, rank) VALUES (?, ?, ?, ?)",
            (int(batch_id), json.dumps(jogo, ensure_ascii=False), float(max_jogos - idx), int(idx)),
        )
    conn.commit()
    return batch_id


def run_predict_next(tipo: int, max_jogos: int, pool_size: int | None, seed: int | None, dry_run: bool) -> dict[str, Any]:
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    ts = now_tag()
    log_file = logs_dir / f"predict_next_{ts}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logger = logging.getLogger("predict_next")

    chosen_seed = int(seed) if seed is not None else random.randint(1, 2_147_483_647)
    random.seed(chosen_seed)

    cfg_meta = _load_json(ROOT / "config" / "meta_controller.json", {"enabled": False})
    cfg_prod = _load_json(ROOT / "config" / "production_research.json", {})
    cfg_port = _load_json(ROOT / "config" / "portfolio.json", {"enabled": False})
    cfg_reward = _load_json(ROOT / "config" / "reward_v2.json", {})
    cfg_perf = _load_json(ROOT / "config" / "performance.json", {})
    cfg_pref = _load_json(ROOT / "config" / "fechamentos_preferencias.json", {})

    logger.info("configs carregados: meta=%s prod=%s portfolio=%s reward=%s perf=%s pref=%s",
                bool(cfg_meta), bool(cfg_prod), bool(cfg_port), bool(cfg_reward), bool(cfg_perf), bool(cfg_pref))
    logger.info("seed=%s", chosen_seed)

    conn = get_conn()
    try:
        ultimo_concurso, ultimo_resultado = _latest_concurso_and_last_result(conn)
        concurso_alvo = int(ultimo_concurso) + 1

        hub = BrainHub(conn)
        loaded_brains = register_brains_auto(conn, hub)
        if not loaded_brains:
            raise RuntimeError("Nenhum cérebro carregado para geração.")
        hub.load_all()

        recipes = ensure_seed_recipes(conn, loaded_brains)
        arms = build_default_arms()

        dummy_stats = {k: type("S", (), {"pulls": 1, "mean_reward": 0.0})() for k in recipes.keys()}
        arm_stats = {a.name: type("A", (), {"pulls": 1, "mean_reward": 0.0})() for a in arms}

        arm = choose_arm_ucb(arms, arm_stats, 1, 1.0, "neutro")
        recipe = choose_recipe_ucb(recipes, dummy_stats, 1, 1.0)
        decision = {"arm": arm.name, "recipe": recipe.name, "exploration_rate": 0.5}

        if bool(cfg_meta.get("enabled", False)):
            mc = MetaController(cfg_meta, model_store=ModelStore())
            feats = extract_context_features(conn, ultimo_concurso)
            decision = mc.decide(feats, [a.name for a in arms], list(recipes.keys()), arm.name, recipe.name)
            arm = next((a for a in arms if a.name == decision.get("arm")), arm)
            recipe = recipes.get(decision.get("recipe"), recipe)

        janela = int(cfg_prod.get("janela_recente", cfg_perf.get("janela_recente", 180)))
        context = build_context(conn, ultimo_concurso, janela)
        per_brain = {bid: max(20, int(max_jogos * 3)) for bid in loaded_brains}
        top_n = max(120, int(max_jogos) * 6)

        candidates = hub.generate_games(context=context, size=int(tipo), per_brain=per_brain, top_n=top_n) or []
        records = _build_candidate_records(candidates, tipo, ultimo_resultado, arm.name, recipe.name)

        logger.info("total candidatos válidos=%s", len(records))
        logger.info("top 5 scores=%s", [round(float(c.get("score", 0.0)), 6) for c in sorted(records, key=lambda x: x.get("score", 0.0), reverse=True)[:5]])

        final_games: list[list[int]] = []
        used_portfolio = False
        try:
            from training.meta.portfolio_builder import PortfolioBuilder

            if bool(cfg_port.get("enabled", True)):
                pb = PortfolioBuilder(cfg_port)
                final_games = pb.build(records, int(max_jogos), mode="production", quotas={})
                used_portfolio = True
        except Exception as exc:
            logger.warning("PortfolioBuilder indisponível/falhou, usando fallback: %s", exc)

        if not final_games:
            final_games = _fallback_select(records, int(max_jogos))

        final_games = [sorted(int(x) for x in jogo) for jogo in final_games[: int(max_jogos)]]
        pool = _suggest_pool(final_games, pool_size)

        even_profile = Counter(sum(1 for d in g if d % 2 == 0) for g in final_games)
        logger.info("diversidade paridade final=%s", dict(sorted(even_profile.items())))

        batch_id = _persist_if_tables_exist(
            conn,
            concurso_alvo=concurso_alvo,
            tipo=int(tipo),
            pool_size=pool_size,
            max_jogos=int(max_jogos),
            seed=chosen_seed,
            arm_name=arm.name,
            recipe_name=recipe.name,
            brains_signature=",".join(sorted(loaded_brains[:12])),
            jogos=final_games,
            dry_run=bool(dry_run),
        )

        export_dir = ROOT / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_payload: dict[str, Any] = {
            "concurso_alvo": concurso_alvo,
            "tipo": int(tipo),
            "pool_size": int(pool_size) if pool_size is not None else None,
            "max_jogos": int(max_jogos),
            "jogos": final_games,
            "dry_run": bool(dry_run),
            "used_portfolio_builder": bool(used_portfolio),
            "log_file": str(log_file),
        }
        if pool is not None:
            export_payload["pool_sugerido"] = pool
        if batch_id is not None:
            export_payload["batch_id"] = int(batch_id)

        export_file = export_dir / f"predict_concurso_{concurso_alvo}_tipo_{tipo}_{ts}.json"
        export_file.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"Último concurso no DB: {ultimo_concurso}")
        print(f"Concurso alvo: {concurso_alvo}")
        print(f"Tipo: {tipo}")
        print(f"Jogos gerados: {len(final_games)}")
        if pool is not None:
            print(f"Pool sugerido: {pool}")
        print(json.dumps(final_games, ensure_ascii=False))

        return {
            "ultimo_concurso": ultimo_concurso,
            "concurso_alvo": concurso_alvo,
            "jogos": final_games,
            "pool_sugerido": pool,
            "export_file": str(export_file),
            "log_file": str(log_file),
            "batch_id": batch_id,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera jogos para o próximo concurso com pipeline estilo backtest_v2.")
    parser.add_argument("--tipo", type=int, default=15, choices=[15, 18])
    parser.add_argument("--max-jogos", type=int, default=30)
    parser.add_argument("--pool-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        run_predict_next(
            tipo=int(args.tipo),
            max_jogos=int(args.max_jogos),
            pool_size=int(args.pool_size) if args.pool_size is not None else None,
            seed=int(args.seed) if args.seed is not None else None,
            dry_run=bool(args.dry_run),
        )
    except Exception as exc:
        print(f"Erro na geração para próximo concurso: {exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
