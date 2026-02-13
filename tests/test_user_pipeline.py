import json
import sqlite3

from training.user.check_hits_pending import check_pending
from training.user.export_games_txt import export_batch
from training.user.generate_for_user import ensure_user_tables


def _mk_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE concursos (
            concurso INTEGER PRIMARY KEY,
            d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
            d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
            d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE memoria_jogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso_n INTEGER, concurso_n1 INTEGER, tipo_jogo INTEGER,
            d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
            d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
            d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
            d16 INTEGER, d17 INTEGER, d18 INTEGER,
            acertos INTEGER, peso REAL, origem TEXT, timestamp TEXT,
            UNIQUE(concurso_n, concurso_n1, tipo_jogo, d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18)
        )
        """
    )
    dezenas = list(range(1, 16))
    conn.execute("INSERT INTO concursos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (100, *dezenas))
    conn.commit()


def test_check_pending_idempotent_and_export(tmp_path, monkeypatch):
    db = tmp_path / "userpipe.db"
    conn = sqlite3.connect(str(db))
    try:
        _mk_db(conn)
        ensure_user_tables(conn)
        conn.execute(
            "INSERT INTO generated_batches(created_at, concurso_alvo, mode, tipo_jogo, fechamento_tipo, pool_size, max_jogos, arm, recipe, brains_signature, exploration_rate, seed, status) VALUES ('t',100,'production',15,'POOL',18,2,'a','r','b',0.5,1,'pending')"
        )
        bid = int(conn.execute("SELECT id FROM generated_batches ORDER BY id DESC LIMIT 1").fetchone()[0])
        conn.execute(
            "INSERT INTO generated_games(batch_id, dezenas_json, score_internal, rank) VALUES (?, ?, 1.0, 1)",
            (bid, json.dumps(list(range(1, 16)))),
        )
        conn.execute(
            "INSERT INTO generated_games(batch_id, dezenas_json, score_internal, rank) VALUES (?, ?, 0.9, 2)",
            (bid, json.dumps([1,2,3,4,5,6,7,8,9,10,11,12,13,14,25])),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("DB_PATH", str(db))

    conn = sqlite3.connect(str(db))
    try:
        r1 = check_pending(conn, auto=True)
        assert r1["checked"] == 1
        # idempotente
        r2 = check_pending(conn, auto=True)
        assert r2["checked"] == 0

        st = conn.execute("SELECT status FROM generated_batches WHERE id=?", (bid,)).fetchone()[0]
        assert st == "checked"
        br = conn.execute("SELECT COUNT(*) FROM batch_results WHERE batch_id=?", (bid,)).fetchone()[0]
        assert int(br) == 1
    finally:
        conn.close()

    out = export_batch(bid, to_csv=False)
    assert out.exists()
