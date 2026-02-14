from __future__ import annotations

import sqlite3


def apply_sqlite_pragmas(conn: sqlite3.Connection, profile: str):
    p = str(profile or "low_cpu")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    if p == "fast":
        conn.execute("PRAGMA cache_size=-80000;")
        conn.execute("PRAGMA mmap_size=134217728;")
    elif p == "balanced":
        conn.execute("PRAGMA cache_size=-50000;")
        conn.execute("PRAGMA mmap_size=67108864;")
    else:
        conn.execute("PRAGMA cache_size=-20000;")
        conn.execute("PRAGMA mmap_size=33554432;")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (str(name),),
    ).fetchone()
    return bool(row)


def ensure_indexes(conn: sqlite3.Connection):
    index_plan = [
        ("concursos", "CREATE INDEX IF NOT EXISTS idx_concursos_concurso ON concursos(concurso)"),
        ("memoria_jogos", "CREATE INDEX IF NOT EXISTS idx_memoria_concurso_n1 ON memoria_jogos(concurso_n1)"),
        ("memoria_jogos", "CREATE INDEX IF NOT EXISTS idx_memoria_tipo_hit ON memoria_jogos(tipo_jogo, acertos)"),
        ("generated_batches", "CREATE INDEX IF NOT EXISTS idx_batches_target_status ON generated_batches(concurso_alvo, status)"),
        ("outcomes", "CREATE INDEX IF NOT EXISTS idx_outcomes_run_step_perf ON outcomes(run_id, step)"),
        ("decisions", "CREATE INDEX IF NOT EXISTS idx_decisions_run_step_perf ON decisions(run_id, step)"),
    ]
    for table_name, ddl in index_plan:
        if _table_exists(conn, table_name):
            conn.execute(ddl)
    conn.commit()
