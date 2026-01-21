from __future__ import annotations
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = ROOT / "data" / "BD" / "temp"
MAIN_DB = ROOT / "data" / "BD" / "lotofacil.db"

# regra: só importar memoria_jogos 14+
MIN_ACERTOS = 14

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def merge_one(temp_db: Path, main_conn: sqlite3.Connection) -> None:
    temp_conn = sqlite3.connect(str(temp_db))
    try:
        if not table_exists(temp_conn, "memoria_jogos"):
            return

        # anexar db temp ao main para fazer INSERT SELECT rápido
        main_conn.execute("ATTACH DATABASE ? AS tdb", (str(temp_db),))

        # memoria_jogos (14+)
        main_conn.execute(
            """
            INSERT OR IGNORE INTO memoria_jogos (
              concurso_n, concurso_n1, tipo_jogo,
              d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,
              acertos, peso, origem, timestamp
            )
            SELECT
              concurso_n, concurso_n1, tipo_jogo,
              d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,
              acertos, peso, origem, timestamp
            FROM tdb.memoria_jogos
            WHERE acertos >= ?
            """,
            (MIN_ACERTOS,),
        )

        # opcional: predicoes_proximo (se existir)
        if table_exists(temp_conn, "predicoes_proximo"):
            # garante tabela no main (seu ensure_pred_table já faz isso, mas aqui é safe)
            # se já existir, só insere
            main_conn.execute(
                """
                INSERT OR IGNORE INTO predicoes_proximo
                SELECT * FROM tdb.predicoes_proximo
                """
            )

        main_conn.execute("DETACH DATABASE tdb")
        main_conn.commit()

    finally:
        temp_conn.close()

def main():
    if not MAIN_DB.exists():
        print(f"❌ MAIN_DB não existe: {MAIN_DB}")
        return

    dbs = sorted(TEMP_DIR.glob("**/*.db"))
    if not dbs:
        print("Sem DBs temp para mesclar.")
        return

    main_conn = sqlite3.connect(str(MAIN_DB))
    try:
        main_conn.execute("PRAGMA journal_mode=WAL;")
        merged = 0
        for db in dbs:
            print(f"🔄 Mesclando: {db}")
            merge_one(db, main_conn)
            # apaga após sucesso
            db.unlink(missing_ok=True)
            merged += 1

        print(f"✅ Mesclagem concluída. DBs processados: {merged}")
        print("🧹 Rodando VACUUM… (pode demorar)")
        main_conn.execute("VACUUM;")
        main_conn.commit()
        print("✅ VACUUM OK")

    finally:
        main_conn.close()

if __name__ == "__main__":
    main()
