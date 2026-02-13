from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.memory.memory_refiner import MemoryRefiner
from training.reporting.telemetry_writer import TelemetryWriter
from training.user.generate_for_user import ensure_user_tables


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: Path, default: dict) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return dict(default)


def _result_for(conn: sqlite3.Connection, concurso: int) -> list[int] | None:
    row = conn.execute(
        "SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15 FROM concursos WHERE concurso=?",
        (int(concurso),),
    ).fetchone()
    return [int(x) for x in row] if row else None


def _ensure_outcomes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            step INTEGER,
            concurso_ref INTEGER,
            hit_max INTEGER,
            reward REAL,
            diversity REAL,
            created_at TEXT
        )
        """
    )
    conn.commit()


def _insert_memoria_raw(conn: sqlite3.Connection, concurso: int, tipo: int, dezenas: list[int], acertos: int) -> None:
    if int(acertos) < 14:
        return
    payload = sorted(set(int(x) for x in dezenas)) + [None] * (18 - len(dezenas))
    payload = payload[:18]
    cols = [
        "concurso_n",
        "concurso_n1",
        "tipo_jogo",
        *[f"d{i}" for i in range(1, 19)],
        "acertos",
        "peso",
        "origem",
        "timestamp",
    ]
    vals = [int(concurso - 1), int(concurso), int(tipo), *payload, int(acertos), 1.0, "user_batch_check", now_str()]
    q = f"INSERT OR IGNORE INTO memoria_jogos({','.join(cols)}) VALUES ({','.join(['?']*len(vals))})"
    conn.execute(q, tuple(vals))


def check_pending(conn: sqlite3.Connection, auto: bool = True) -> dict:
    ensure_user_tables(conn)
    _ensure_outcomes(conn)

    rows = conn.execute(
        """
        SELECT id, concurso_alvo, tipo_jogo, status
        FROM generated_batches
        WHERE status='pending'
        ORDER BY id ASC
        """
    ).fetchall()

    checked = 0
    for batch_id, concurso_alvo, tipo_jogo, status in rows:
        result = _result_for(conn, int(concurso_alvo))
        if not result:
            continue

        exists = conn.execute("SELECT 1 FROM batch_results WHERE batch_id=?", (int(batch_id),)).fetchone()
        if exists:
            conn.execute("UPDATE generated_batches SET status='checked' WHERE id=?", (int(batch_id),))
            conn.commit()
            continue

        games = conn.execute(
            "SELECT id, dezenas_json, rank FROM generated_games WHERE batch_id=? ORDER BY rank ASC",
            (int(batch_id),),
        ).fetchall()

        hits_dist = {"12": 0, "13": 0, "14": 0, "15": 0}
        hit_max = 0
        best_game_id = None
        for gid, dezenas_json, _ in games:
            dezenas = json.loads(dezenas_json or "[]")
            h = len(set(int(x) for x in dezenas) & set(result))
            hit_max = max(hit_max, h)
            if best_game_id is None or h >= hit_max:
                best_game_id = int(gid)
            if h >= 12:
                k = str(min(15, h))
                if k in hits_dist:
                    hits_dist[k] += 1
            _insert_memoria_raw(conn, int(concurso_alvo), int(tipo_jogo), dezenas, h)

        conn.execute(
            """
            INSERT INTO batch_results(batch_id, concurso_num, checked_at, hit_max, hits_json, best_game_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (int(batch_id), int(concurso_alvo), now_str(), int(hit_max), json.dumps(hits_dist, ensure_ascii=False), int(best_game_id) if best_game_id else None),
        )
        conn.execute("UPDATE generated_batches SET status='checked' WHERE id=?", (int(batch_id),))
        conn.execute(
            "INSERT INTO outcomes(run_id, step, concurso_ref, hit_max, reward, diversity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (None, int(batch_id), int(concurso_alvo), int(hit_max), float(hit_max), 0.0, now_str()),
        )
        conn.commit()
        checked += 1

    # telemetry + refiner
    tw = TelemetryWriter(conn, _load_json(ROOT / "config" / "reporting.json", {"enabled": True}))
    tw.log_summary_step(0, checked, {"checked_batches": checked, "source": "check_hits_pending"})

    ref_cfg = _load_json(ROOT / "config" / "memory_refiner.json", {"enabled": False})
    if bool(ref_cfg.get("enabled", False)):
        refiner = MemoryRefiner(conn, ref_cfg)
        try:
            refiner.run_batch(batch_size=min(500, int(ref_cfg.get("batch_size", 2000))))
        except Exception:
            pass

    return {"checked": checked}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--auto", action="store_true")
    args = p.parse_args()

    conn = get_conn()
    try:
        out = check_pending(conn, auto=args.auto)
        print(json.dumps(out, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
