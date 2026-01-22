# START/startBD.py
from __future__ import annotations

import os

import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

# ======================================================
# 🔧 GARANTE ROOT DO PROJETO NO PYTHONPATH
# ======================================================
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# agora os imports funcionam sempre
from config.paths import SCHEMA_PATH, CSV_PATH
from data.BD.connection import get_conn


# ======================================================
# UTIL
# ======================================================
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}")


# ======================================================
# SCHEMA
# ======================================================
def criar_schema(conn):
    log("🧱 Criando/validando schema do banco...")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    log("✅ Schema OK")


# ======================================================
# IMPORTAÇÃO CSV (SEM DUPLICAR)
# ======================================================
def importar_csv_sem_duplicar(conn, csv_path: Path):
    log(f"📥 Lendo CSV: {csv_path}")
    df = pd.read_csv(csv_path, sep=";")

    cur = conn.cursor()

    log(f"📌 CSV carregado: {len(df)} concursos")

    # --------------------------------------------------
    # INSERÇÃO INCREMENTAL
    # --------------------------------------------------
    log("🗄️ Inserindo concursos (sem duplicar)...")
    inseridos = 0

    for _, row in df.iterrows():
        concurso = int(row.iloc[0])
        dezenas = [int(row.iloc[i]) for i in range(1, 16)]

        cur.execute(
            """
            INSERT OR IGNORE INTO concursos (
                concurso,
                d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [concurso] + dezenas,
        )
        inseridos += cur.rowcount

    conn.commit()
    log(f"✅ Inseridos: {inseridos} | Ignorados (duplicados): {len(df) - inseridos}")

    # --------------------------------------------------
    # RECONSTRÓI FREQUÊNCIAS (CACHE)
    # --------------------------------------------------
    log("📊 Recalculando tabela 'frequencias'...")
    cur.execute("DELETE FROM frequencias")

    contagem = {i: 0 for i in range(1, 26)}

    cur.execute(
        """
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        """
    )
    for row in cur.fetchall():
        for dez in row:
            contagem[int(dez)] += 1

    total = sum(contagem.values()) or 1

    for numero, qtd in contagem.items():
        peso = qtd / total
        cur.execute(
            """
            INSERT INTO frequencias (numero, quantidade, peso, atualizado_em)
            VALUES (?, ?, ?, ?)
            """,
            (numero, qtd, peso, now()),
        )

    conn.commit()
    log("✅ Frequências atualizadas")


# ======================================================
# MAIN
# ======================================================
def main():
    try:
        db_override = os.getenv("DB_PATH")
        conn = get_conn(db_override) if db_override else get_conn()
        criar_schema(conn)

        if not CSV_PATH.exists():
            log(f"❌ CSV não encontrado: {CSV_PATH}")
            sys.exit(1)

        importar_csv_sem_duplicar(conn, CSV_PATH)

        log("🎉 Banco pronto para uso!")

    except Exception as e:
        log(f"❌ ERRO: {e}")
        raise

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
