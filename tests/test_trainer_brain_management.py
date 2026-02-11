import sqlite3

from training.trainer_v2 import (
    _build_dynamic_per_brain_map,
    _compute_brain_enable_decisions,
    _ensure_runtime_governance_tables,
)


def test_compute_brain_enable_decisions_disables_q15_zero_with_volume() -> None:
    perf = [
        {"brain_id": "brain_strong", "jogos": 10000, "media": 10.0, "q14": 100, "q15": 10},
        {"brain_id": "brain_weak", "jogos": 10000, "media": 9.5, "q14": 20, "q15": 0},
        {"brain_id": "brain_new", "jogos": 500, "media": 9.0, "q14": 1, "q15": 0},
    ]
    decisions = _compute_brain_enable_decisions(
        perf,
        min_games=3000,
        keep_top_q15=1,
        keep_top_q14=1,
    )

    assert decisions["brain_strong"] is True
    assert decisions["brain_weak"] is False
    assert decisions["brain_new"] is True


def test_compute_brain_enable_decisions_protects_top_q14_even_q15_zero() -> None:
    perf = [
        {"brain_id": "brain_top_q14", "jogos": 20000, "media": 9.8, "q14": 500, "q15": 0},
        {"brain_id": "brain_other", "jogos": 20000, "media": 9.8, "q14": 20, "q15": 0},
    ]
    decisions = _compute_brain_enable_decisions(
        perf,
        min_games=3000,
        keep_top_q15=0,
        keep_top_q14=1,
    )

    assert decisions["brain_top_q14"] is True
    assert decisions["brain_other"] is False


def test_compute_brain_enable_decisions_with_recent_weight_prefers_recent() -> None:
    perf = [
        {
            "brain_id": "brain_recent_hot",
            "jogos": 10000,
            "media": 9.5,
            "q14": 20,
            "q15": 0,
            "q14_recent": 50,
            "q15_recent": 5,
            "media_recent": 10.5,
        },
        {
            "brain_id": "brain_old_hot",
            "jogos": 10000,
            "media": 10.0,
            "q14": 200,
            "q15": 0,
            "q14_recent": 1,
            "q15_recent": 0,
            "media_recent": 9.0,
        },
    ]
    decisions = _compute_brain_enable_decisions(
        perf,
        min_games=3000,
        keep_top_q15=1,
        keep_top_q14=0,
        recent_weight=0.95,
    )

    assert decisions["brain_recent_hot"] is True


def test_build_dynamic_per_brain_map_allocates_more_to_better_recent_brain() -> None:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE cerebros (id INTEGER PRIMARY KEY AUTOINCREMENT, brain_id TEXT UNIQUE NOT NULL, nome TEXT, categoria TEXT, versao TEXT, habilitado INTEGER DEFAULT 1, criado_em TEXT, atualizado_em TEXT)"
    )
    cur.execute(
        "CREATE TABLE cerebro_performance (id INTEGER PRIMARY KEY AUTOINCREMENT, cerebro_id INTEGER NOT NULL, concurso INTEGER NOT NULL, jogos_gerados INTEGER DEFAULT 0, media_pontos REAL DEFAULT 0, qtd_11 INTEGER DEFAULT 0, qtd_12 INTEGER DEFAULT 0, qtd_13 INTEGER DEFAULT 0, qtd_14 INTEGER DEFAULT 0, qtd_15 INTEGER DEFAULT 0, atualizado_em TEXT, UNIQUE(cerebro_id, concurso))"
    )
    cur.execute("INSERT INTO cerebros (brain_id) VALUES ('brain_a')")
    cur.execute("INSERT INTO cerebros (brain_id) VALUES ('brain_b')")
    cur.execute("SELECT id, brain_id FROM cerebros")
    ids = {bid: cid for cid, bid in cur.fetchall()}

    # brain_a recente melhor
    cur.execute(
        "INSERT INTO cerebro_performance (cerebro_id, concurso, jogos_gerados, media_pontos, qtd_14, qtd_15) VALUES (?,?,?,?,?,?)",
        (ids["brain_a"], 100, 100, 10.2, 8, 2),
    )
    cur.execute(
        "INSERT INTO cerebro_performance (cerebro_id, concurso, jogos_gerados, media_pontos, qtd_14, qtd_15) VALUES (?,?,?,?,?,?)",
        (ids["brain_b"], 100, 100, 9.6, 2, 0),
    )
    conn.commit()

    alloc = _build_dynamic_per_brain_map(conn, base_per_brain=80, size=15, recent_window=30)
    assert alloc
    assert alloc["brain_a"] > alloc["brain_b"]


def test_ensure_runtime_governance_tables_creates_missing_tables() -> None:
    conn = sqlite3.connect(":memory:")
    _ensure_runtime_governance_tables(conn)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='experimentos'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='experimentos_resultados'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cerebros'")
    assert cur.fetchone() is not None
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cerebro_performance'")
    assert cur.fetchone() is not None
