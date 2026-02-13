import sqlite3

from training.memory.memory_audit import ensure_memory_tables, sanity_report
from training.memory.memory_refiner import MemoryRefiner


def _create_raw_memoria(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE memoria_jogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso_n INTEGER,
            concurso_n1 INTEGER,
            tipo_jogo INTEGER,
            d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
            d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
            d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
            d16 INTEGER, d17 INTEGER, d18 INTEGER,
            acertos INTEGER,
            peso REAL,
            origem TEXT,
            timestamp TEXT
        )
        """
    )

    for i in range(1, 301):
        tipo = 15 if i % 2 == 0 else 18
        base = (i % 25) + 1
        dezenas = [((base + j - 1) % 25) + 1 for j in range(tipo)]
        if tipo == 15:
            dezenas = dezenas + [None, None, None]
        acertos = 15 if i % 50 == 0 else (14 if i % 9 == 0 else (13 if i % 5 == 0 else 12))
        if i % 33 == 0:
            acertos = 10
        conn.execute(
            "INSERT INTO memoria_jogos(concurso_n,concurso_n1,tipo_jogo,d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,acertos,peso,origem,timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, i + 1, tipo, *dezenas, acertos, 1.0, f"smart:a:r:{i%7}", "2024-01-01 00:00:00"),
        )
    conn.commit()


def test_memory_refiner_batches_and_compression():
    conn = sqlite3.connect(":memory:")
    try:
        _create_raw_memoria(conn)
        ensure_memory_tables(conn)

        cfg = {
            "enabled": True,
            "batch_size": 80,
            "gold_threshold": 0.72,
            "quarantine_threshold": 0.35,
            "min_hit_gold": 13,
            "allow_12_in_gold": False,
            "clone_threshold": 0.78,
            "max_gold_size": 500,
            "compress_mode": "delete_redundant",
        }
        refiner = MemoryRefiner(conn, cfg)

        r1 = refiner.run_batch(80)
        r2 = refiner.run_batch(80)
        r3 = refiner.run_batch(80)

        assert r1["processed"] > 0
        assert r2["processed"] > 0
        assert r3["processed"] > 0

        report = sanity_report(conn)
        assert report["gold_size"] > 0
        assert report["quarantine_size"] > 0
        assert report["audit_size"] >= (r1["processed"] + r2["processed"] + r3["processed"])

        raw_count = int(conn.execute("SELECT COUNT(*) FROM memoria_jogos").fetchone()[0])
        assert raw_count == 300
    finally:
        conn.close()
