from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from config.paths import DB_PATH
except Exception:
    DB_PATH = ROOT / "data" / "BD" / "lotofacil.db"

from training.core.brain_hub import BrainHub
from training.fechamentos_posicionais.auto_select import AutoSelectConfig, pick_pool_and_fixed
from training.fechamentos_posicionais.brain_adapter import register_all_brains
from training.fechamentos_posicionais.context import build_context
from training.fechamentos_posicionais.export import to_json, to_txt
from training.fechamentos_posicionais.generator import generate_fechamento
from training.fechamentos_posicionais.grouping import plan_groups
from training.fechamentos_posicionais.registry import get_spec, list_specs


def _get_conn() -> sqlite3.Connection:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_available_specs() -> None:
    print("Fechamentos posicionais disponíveis:")
    for spec in list_specs():
        print(f"- {spec.code}: {spec.name}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Gerar fechamento posicional automático (sem escolha manual)")
    parser.add_argument("--code", help="Código do fechamento (ex: FC93)")
    parser.add_argument("--list", action="store_true", help="Listar fechamentos posicionais disponíveis")
    parser.add_argument("--qtd", type=int, default=1, help="Quantidade de rodadas")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade")
    parser.add_argument("--date", help="Data base do concurso (YYYY-MM-DD)")
    parser.add_argument("--out", help="Salvar JSON em arquivo")
    parser.add_argument("--out-txt", help="Salvar TXT em arquivo")
    args = parser.parse_args(argv)

    if args.list or not args.code:
        _print_available_specs()
        if not args.list:
            print("\nInforme o código desejado usando --code.")
        return 0

    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError as exc:
            raise SystemExit(f"Data inválida: {exc}")

    conn = _get_conn()
    hub = BrainHub(conn)
    register_all_brains(conn, hub)
    hub.load_all()

    context = build_context(conn, args.date)
    spec = get_spec(args.code)

    results = []
    for idx in range(args.qtd):
        rng_seed = args.seed + idx if args.seed is not None else None
        rng = random.Random(rng_seed)
        pool, fixed, meta = pick_pool_and_fixed(spec, hub, context, rng, AutoSelectConfig())
        group_plan = plan_groups(spec, pool, fixed, hub, context, rng)
        result = generate_fechamento(
            spec,
            pool,
            fixed,
            group_plan.groups,
            hub,
            context=context,
            rng=rng,
            selection_metadata={**meta, "groups": group_plan.metadata},
        )
        results.append(result)

    payload = [to_json(result) for result in results]
    txt_blocks = [to_txt(result) for result in results]

    output_json = json.dumps(payload, ensure_ascii=False, indent=2)
    output_txt = "\n\n".join(txt_blocks)

    if args.out:
        _write_output(Path(args.out), output_json)
    else:
        print(output_json)

    if args.out_txt:
        _write_output(Path(args.out_txt), output_txt)
    else:
        print("\n" + output_txt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
