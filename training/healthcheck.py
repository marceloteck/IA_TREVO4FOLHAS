from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from data.BD.connection import get_conn
from training.meta.checkpoint import CheckpointManager


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def run_healthcheck() -> int:
    rc = 0
    conn: sqlite3.Connection = get_conn()
    try:
        row = conn.execute("SELECT MIN(concurso), MAX(concurso), COUNT(1) FROM concursos").fetchone()
        if not row or int(row[2] or 0) <= 0:
            _fail("Tabela concursos vazia ou ausente")
            return 2
        min_c, max_c, count_c = int(row[0]), int(row[1]), int(row[2])
        _ok(f"concursos range={min_c}..{max_c} total={count_c}")

        ck_row = conn.execute("SELECT ultimo_concurso_processado, etapa, timestamp FROM checkpoint WHERE id=1").fetchone()
        if ck_row:
            ck_val = int(ck_row[0] or 0)
            if min_c <= ck_val <= max_c:
                _ok(f"checkpoint tabela principal válido: {ck_val}")
            else:
                _warn(f"checkpoint principal fora do range: {ck_val} (esperado {min_c}..{max_c})")
                rc = max(rc, 1)
        else:
            _warn("checkpoint principal inexistente")
            rc = max(rc, 1)

        manager = CheckpointManager(conn, {"enabled": True, "max_keep_checkpoints": 10})
        latest = manager.load_latest_valid_any_running()
        if latest is None:
            _warn("checkpoint meta válido não encontrado para runs em execução")
            rc = max(rc, 1)
        else:
            concurso_ref = int(latest.get("concurso_ref", 0))
            step_global = int(latest.get("step_global", latest.get("step", 0)))
            if step_global < 0:
                _warn(f"step_global inválido: {step_global}")
                rc = max(rc, 1)
            if not (min_c <= concurso_ref <= max_c):
                _warn(f"concurso_ref fora do range no meta checkpoint: {concurso_ref}")
                rc = max(rc, 1)
            else:
                _ok(f"meta checkpoint válido step_global={step_global} concurso_ref={concurso_ref}")

        inc = Path("logs/checkpoint_incremental.json")
        if inc.exists():
            try:
                payload = json.loads(inc.read_text(encoding="utf-8"))
                _ok(
                    "checkpoint incremental encontrado "
                    f"step_global={int(payload.get('step_global', 0))} concurso_ref={int(payload.get('concurso_ref', 0))}"
                )
            except Exception as exc:
                _warn(f"checkpoint incremental corrompido: {exc}")
                rc = max(rc, 1)
        else:
            _warn("checkpoint incremental ainda não criado")
            rc = max(rc, 1)

    except Exception as exc:
        _fail(f"healthcheck falhou: {exc}")
        return 2
    finally:
        conn.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(run_healthcheck())
