# data/BD/connection.py

import sqlite3
from pathlib import Path

# ===============================
# 📌 CAMINHO CENTRAL DO BANCO
# ===============================

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lotofacil.db"


# ===============================
# 🔌 CONEXÃO COM SQLITE
# ===============================

def get_conn():
    """
    Retorna uma conexão SQLite válida.
    Cria diretórios automaticamente se necessário.
    """
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # acesso por nome de coluna
    return conn
