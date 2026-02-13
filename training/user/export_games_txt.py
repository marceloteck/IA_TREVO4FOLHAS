from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn


def export_batch(batch_id: int, to_csv: bool = False) -> Path:
    conn = get_conn()
    try:
        row = conn.execute("SELECT concurso_alvo FROM generated_batches WHERE id=?", (int(batch_id),)).fetchone()
        if not row:
            raise RuntimeError(f"batch_id {batch_id} não encontrado")
        concurso = int(row[0])
        games = conn.execute("SELECT rank, dezenas_json FROM generated_games WHERE batch_id=? ORDER BY rank", (int(batch_id),)).fetchall()

        if to_csv:
            out = ROOT / "exports" / f"jogos_concurso_{concurso}_batch_{batch_id}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as f:
                f.write("rank,dezenas\n")
                for rank, dezenas_json in games:
                    dezenas = json.loads(dezenas_json or "[]")
                    f.write(f"{rank},\"{' '.join(f'{int(d):02d}' for d in dezenas)}\"\n")
        else:
            out = ROOT / "exports" / f"jogos_concurso_{concurso}_batch_{batch_id}.txt"
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("w", encoding="utf-8") as f:
                f.write(f"batch_id={batch_id} concurso_alvo={concurso}\n")
                for rank, dezenas_json in games:
                    dezenas = json.loads(dezenas_json or "[]")
                    f.write(f"{int(rank):03d}: {' '.join(f'{int(d):02d}' for d in dezenas)}\n")
        return out
    finally:
        conn.close()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--batch-id", type=int, required=True)
    p.add_argument("--csv", action="store_true")
    args = p.parse_args()

    out = export_batch(args.batch_id, to_csv=args.csv)
    print(str(out))


if __name__ == "__main__":
    main()
