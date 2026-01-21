# data/BD/connection.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _resolve_db_path(db_path: str | None) -> Path:
    # 1) parâmetro explícito > 2) ENV DB_PATH > 3) config.paths.DB_PATH > 4) fallback antigo
    if db_path is None:
        db_path = os.getenv("DB_PATH")

    if db_path:
        path = Path(db_path)
    else:
        try:
            from config.paths import DB_PATH as CFG_DB_PATH
            path = Path(CFG_DB_PATH)
        except Exception:
            root = Path(__file__).resolve().parents[2]
            path = root / "data" / "BD" / "lotofacil.db"

    return path


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # timeout ajuda em runs longos com muitas escritas
    conn = sqlite3.connect(str(path), timeout=60)

    # Pragmas de performance/segurança (com fallback)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")

    # WAL é ótimo, mas pode falhar em alguns FS/ambientes -> fallback seguro
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE;")

    return conn
