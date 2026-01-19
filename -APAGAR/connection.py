import sqlite3
import os

DB_PATH = "data/BD/lotofacil.db"

def get_conn():
    if not os.path.exists("data"):
        os.makedirs("data")

    conn = sqlite3.connect(DB_PATH)
    return conn
