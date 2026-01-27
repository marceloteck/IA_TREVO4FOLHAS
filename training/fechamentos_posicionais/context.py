from __future__ import annotations

import sqlite3
from typing import Dict, Optional


def fetch_concurso_by_date(conn: sqlite3.Connection, date_str: str) -> Optional[int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT concurso
        FROM concursos
        WHERE data <= ?
        ORDER BY data DESC
        LIMIT 1
        """,
        (date_str,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def fetch_latest_concurso(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT MAX(concurso) FROM concursos")
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def fetch_recent_results(conn: sqlite3.Connection, concurso_n: int, janela: int) -> list[list[int]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        WHERE concurso <= ?
        ORDER BY concurso DESC
        LIMIT ?
        """,
        (int(concurso_n), int(janela)),
    )
    rows = list(reversed(cur.fetchall()))
    return [[int(x) for x in r] for r in rows]


def build_context(conn: sqlite3.Connection, date_str: Optional[str] = None, janela: int = 120) -> Dict[str, object]:
    if date_str:
        concurso_n = fetch_concurso_by_date(conn, date_str)
    else:
        concurso_n = fetch_latest_concurso(conn)

    if concurso_n is None:
        raise RuntimeError("Banco não possui concursos. Rode START/startBD.py.")

    historico = fetch_recent_results(conn, concurso_n=concurso_n, janela=janela)
    ultimo_resultado = historico[-1] if historico else []

    freq = {i: 0 for i in range(1, 26)}
    for resultado in historico:
        for dezena in resultado:
            freq[int(dezena)] += 1

    context = {
        "concurso_n": int(concurso_n),
        "ultimo_resultado": ultimo_resultado,
        "historico_recente": historico,
        "freq_recente": freq,
        "janela_recente": int(janela),
    }
    if date_str:
        context["date"] = date_str
    return context
