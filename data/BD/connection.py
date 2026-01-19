# data/BD/connection.py
import sqlite3
from config.paths import DB_PATH, BD_DIR

def get_conn() -> sqlite3.Connection:
    BD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn
