# data/BD/connection.py
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = os.getenv("DB_PATH")  # <- permite Actions apontar pro DB temporário

    if db_path:
        path = Path(db_path)
    else:
        # fallback antigo (mantém compatibilidade)
        try:
            from config.paths import DB_PATH as CFG_DB_PATH
            path = Path(CFG_DB_PATH)
        except Exception:
            root = Path(__file__).resolve().parents[2]
            path = root / "data" / "BD" / "lotofacil.db"

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn