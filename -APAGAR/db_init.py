import sqlite3
from pathlib import Path

DB_PATH = Path("data/BD/lotofacil.db")
SCHEMA_PATH = Path("data/database/db_schema.sql")

def criar_banco():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    conn.commit()
    conn.close()

    print("✅ Banco SQLite estruturado com schema profissional.")

if __name__ == "__main__":
    criar_banco()
