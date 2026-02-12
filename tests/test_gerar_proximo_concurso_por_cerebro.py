from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from START import gerar_proximo_concurso as gpc


class DummyBrain:
    def __init__(self, bid: str):
        self.id = bid

    def load_state(self) -> None:
        return None

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        base = list(range(1, 26))
        out = []
        for i in range(n):
            start = i % (25 - size + 1)
            out.append(base[start : start + size])
        return out

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        return float(sum(jogo))


def _build_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE concursos (
            concurso INTEGER UNIQUE NOT NULL,
            d1 INTEGER,d2 INTEGER,d3 INTEGER,d4 INTEGER,d5 INTEGER,
            d6 INTEGER,d7 INTEGER,d8 INTEGER,d9 INTEGER,d10 INTEGER,
            d11 INTEGER,d12 INTEGER,d13 INTEGER,d14 INTEGER,d15 INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE cerebros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brain_id TEXT UNIQUE NOT NULL,
            nome TEXT,
            categoria TEXT,
            versao TEXT,
            habilitado INTEGER DEFAULT 1,
            criado_em TEXT,
            atualizado_em TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE cerebro_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cerebro_id INTEGER NOT NULL,
            concurso INTEGER NOT NULL,
            jogos_gerados INTEGER DEFAULT 0,
            media_pontos REAL DEFAULT 0,
            qtd_11 INTEGER DEFAULT 0,
            qtd_12 INTEGER DEFAULT 0,
            qtd_13 INTEGER DEFAULT 0,
            qtd_14 INTEGER DEFAULT 0,
            qtd_15 INTEGER DEFAULT 0
        )
        """
    )

    # concurso base
    cur.execute(
        "INSERT INTO concursos VALUES (1,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15)"
    )

    # cérebros e performance
    cur.execute("INSERT INTO cerebros (brain_id, habilitado) VALUES ('brain_a',1)")
    cur.execute("INSERT INTO cerebros (brain_id, habilitado) VALUES ('brain_b',1)")
    cur.execute("SELECT id, brain_id FROM cerebros")
    ids = {bid: cid for cid, bid in cur.fetchall()}
    cur.execute(
        "INSERT INTO cerebro_performance (cerebro_id, concurso, jogos_gerados, media_pontos, qtd_14, qtd_15) VALUES (?,?,?,?,?,?)",
        (ids["brain_a"], 1, 100, 10.1, 4, 1),
    )
    cur.execute(
        "INSERT INTO cerebro_performance (cerebro_id, concurso, jogos_gerados, media_pontos, qtd_14, qtd_15) VALUES (?,?,?,?,?,?)",
        (ids["brain_b"], 1, 100, 9.9, 2, 0),
    )
    conn.commit()
    return conn


def test_fetch_top_brain_ids_by_performance_orders_by_q15_q14_media() -> None:
    conn = _build_conn()
    ids = gpc.fetch_top_brain_ids_by_performance(conn, limit=2, include_disabled=False)
    assert ids[0] == "brain_a"
    assert ids[1] == "brain_b"


def test_generate_por_cerebro_top_creates_report(monkeypatch) -> None:
    conn = _build_conn()

    def fake_load_brains(_conn):
        return {"brain_a": DummyBrain("brain_a"), "brain_b": DummyBrain("brain_b")}

    monkeypatch.setattr(gpc, "_load_brains_auto", fake_load_brains)

    out = gpc.generate_por_cerebro_top(
        conn=conn,
        size=15,
        janela=50,
        per_brain=5,
        top_brains=1,
        perfil="balanceado",
        include_disabled_brains=False,
        selected_brain_ids=None,
        split_files=True,
    )

    assert out.exists()
    txt = out.read_text(encoding="utf-8")
    assert "CATÁLOGO DE JOGOS POR CÉREBRO" in txt
    assert "brain_a" in txt
    assert "arquivo_txt_cerebro=" in txt
