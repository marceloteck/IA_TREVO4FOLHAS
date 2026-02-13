from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Dict


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_memory_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memoria_jogos_gold (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_memoria_id INTEGER,
            concurso_ref INTEGER,
            tipo_jogo INTEGER,
            dezenas_json TEXT,
            hit INTEGER,
            quality_score REAL,
            context_signature TEXT,
            strategy_signature TEXT,
            diversity_tag TEXT,
            validated INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_gold_hit ON memoria_jogos_gold(hit);
        CREATE INDEX IF NOT EXISTS idx_gold_tipo ON memoria_jogos_gold(tipo_jogo);

        CREATE TABLE IF NOT EXISTS memoria_jogos_quarantine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_memoria_id INTEGER,
            concurso_ref INTEGER,
            tipo_jogo INTEGER,
            dezenas_json TEXT,
            hit INTEGER,
            quality_score REAL,
            reason_flags TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_quar_hit ON memoria_jogos_quarantine(hit);

        CREATE TABLE IF NOT EXISTS memoria_jogos_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_memoria_id INTEGER,
            action TEXT,
            from_layer TEXT,
            to_layer TEXT,
            quality_score REAL,
            reason_flags TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_source ON memoria_jogos_audit(source_memoria_id);

        CREATE TABLE IF NOT EXISTS memory_refiner_state (
            id INTEGER PRIMARY KEY CHECK (id=1),
            last_memoria_id INTEGER DEFAULT 0,
            updated_at TEXT
        );
        """
    )
    conn.commit()


def audit_action(
    conn: sqlite3.Connection,
    source_memoria_id: int,
    action: str,
    from_layer: str,
    to_layer: str,
    quality_score: float,
    reason_flags: list[str],
) -> None:
    conn.execute(
        """
        INSERT INTO memoria_jogos_audit(source_memoria_id, action, from_layer, to_layer, quality_score, reason_flags, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(source_memoria_id),
            str(action),
            str(from_layer),
            str(to_layer),
            float(quality_score),
            json.dumps(reason_flags, ensure_ascii=False),
            now_str(),
        ),
    )


def sanity_report(conn: sqlite3.Connection) -> Dict[str, object]:
    gold = int(conn.execute("SELECT COUNT(*) FROM memoria_jogos_gold").fetchone()[0])
    quar = int(conn.execute("SELECT COUNT(*) FROM memoria_jogos_quarantine").fetchone()[0])
    audit = int(conn.execute("SELECT COUNT(*) FROM memoria_jogos_audit").fetchone()[0])

    hit_gold = dict(conn.execute("SELECT hit, COUNT(*) FROM memoria_jogos_gold GROUP BY hit").fetchall())
    hit_quar = dict(conn.execute("SELECT hit, COUNT(*) FROM memoria_jogos_quarantine GROUP BY hit").fetchall())

    top_flags_rows = conn.execute(
        """
        SELECT reason_flags, COUNT(*) c
        FROM memoria_jogos_audit
        GROUP BY reason_flags
        ORDER BY c DESC
        LIMIT 10
        """
    ).fetchall()

    top_strategy_rows = conn.execute(
        """
        SELECT strategy_signature, COUNT(*) c
        FROM memoria_jogos_gold
        GROUP BY strategy_signature
        ORDER BY c DESC
        LIMIT 10
        """
    ).fetchall()

    return {
        "gold_size": gold,
        "quarantine_size": quar,
        "audit_size": audit,
        "hit_gold": hit_gold,
        "hit_quarantine": hit_quar,
        "top_flags": [{"flags": f, "count": int(c)} for f, c in top_flags_rows],
        "top_strategy_signature": [{"strategy_signature": s, "count": int(c)} for s, c in top_strategy_rows],
    }
