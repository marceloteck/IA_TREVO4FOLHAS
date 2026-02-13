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


def ensure_indexes(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_concursos_concurso ON concursos(concurso);
        CREATE INDEX IF NOT EXISTS idx_memoria_concurso_n1 ON memoria_jogos(concurso_n1);
        CREATE INDEX IF NOT EXISTS idx_memoria_tipo_hit ON memoria_jogos(tipo_jogo, acertos);
        CREATE INDEX IF NOT EXISTS idx_batches_target_status ON generated_batches(concurso_alvo, status);
        CREATE INDEX IF NOT EXISTS idx_outcomes_run_step_perf ON outcomes(run_id, step);
        CREATE INDEX IF NOT EXISTS idx_decisions_run_step_perf ON decisions(run_id, step);
        """
    )
    conn.commit()
