import sqlite3
from unittest import mock

from training.healthcheck import run_healthcheck
from training.meta.checkpoint import CheckpointManager


def _build_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE concursos(concurso INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO concursos(concurso) VALUES (?)", [(i,) for i in range(1, 21)])
    conn.execute("CREATE TABLE checkpoint(id INTEGER PRIMARY KEY, ultimo_concurso_processado INTEGER, etapa TEXT, timestamp TEXT)")
    conn.execute("INSERT INTO checkpoint(id, ultimo_concurso_processado, etapa, timestamp) VALUES (1, 10, 't', 'now')")
    conn.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute("INSERT INTO runs(id, status) VALUES (1, 'running')")
    ck = CheckpointManager(conn, {"enabled": True})
    ck.save({"run_id": 1, "step": 5, "step_global": 5, "concurso_ref": 10})
    conn.commit()
    return conn


def test_healthcheck_ok_with_valid_minimal_db():
    conn = _build_conn()
    try:
        with mock.patch("training.healthcheck.get_conn", return_value=conn):
            rc = run_healthcheck()
        assert rc in {0, 1}
    finally:
        conn.close()
