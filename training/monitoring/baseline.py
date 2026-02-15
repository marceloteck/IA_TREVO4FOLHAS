from __future__ import annotations

from collections import Counter
import sqlite3
from pathlib import Path
from typing import Any, Dict


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _open_conn(db_path: str | Path) -> sqlite3.Connection:
    return sqlite3.connect(str(db_path))


def _fetch_concursos(conn: sqlite3.Connection, limit: int) -> list[tuple[Any, ...]]:
    return conn.execute(
        """
        SELECT concurso, d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        ORDER BY concurso DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def _proxy_from_concursos(rows_desc: list[tuple[Any, ...]], window_w: int) -> Dict[str, float]:
    rows = list(reversed(rows_desc))
    freq_q14 = 0
    copy_q14 = 0
    evaluated = 0

    for idx in range(1, len(rows)):
        hist = rows[max(0, idx - int(window_w)) : idx]
        if not hist:
            continue
        freq = Counter()
        for r in hist:
            for d in r[1:]:
                if d is not None:
                    freq[int(d)] += 1

        pred_freq = {d for d, _ in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:15]}
        pred_copy = {int(d) for d in hist[-1][1:] if d is not None}
        result = {int(d) for d in rows[idx][1:] if d is not None}
        if len(pred_freq) != 15 or len(pred_copy) != 15 or len(result) != 15:
            continue

        if len(pred_freq & result) >= 14:
            freq_q14 += 1
        if len(pred_copy & result) >= 14:
            copy_q14 += 1
        evaluated += 1

    if evaluated <= 0:
        return {
            "frequencia_recente_q14_rate": 0.0,
            "copiar_ultimo_q14_rate": 0.0,
            "num_outcomes": 0,
            "source": "proxy_concursos_empty",
        }

    return {
        "frequencia_recente_q14_rate": _clamp01(freq_q14 / float(evaluated)),
        "copiar_ultimo_q14_rate": _clamp01(copy_q14 / float(evaluated)),
        "num_outcomes": int(evaluated),
        "source": "proxy_concursos",
    }


def compute_baseline_from_db(
    db_path: str | Path | sqlite3.Connection,
    n_min: int = 500,
    n_max: int = 5000,
    window: int | None = None,
) -> Dict[str, float]:
    conn: sqlite3.Connection | None = None
    own_conn = False
    try:
        if isinstance(db_path, sqlite3.Connection):
            conn = db_path
        else:
            conn = _open_conn(db_path)
            own_conn = True

        max_rows = max(50, int(n_max) + 1)
        rows = _fetch_concursos(conn, max_rows)
        if not rows:
            return {
                "frequencia_recente_q14_rate": 0.0,
                "copiar_ultimo_q14_rate": 0.0,
                "num_outcomes": 0,
                "source": "no_rows",
            }

        w = max(5, int(window) if window is not None else 30)
        out = _proxy_from_concursos(rows, window_w=w)
        out["window"] = int(w)
        out["n_min"] = int(max(1, n_min))
        out["n_max"] = int(max(1, n_max))
        return out
    except Exception:
        return {
            "frequencia_recente_q14_rate": 0.0,
            "copiar_ultimo_q14_rate": 0.0,
            "num_outcomes": 0,
            "source": "error",
        }
    finally:
        if own_conn and conn is not None:
            conn.close()
