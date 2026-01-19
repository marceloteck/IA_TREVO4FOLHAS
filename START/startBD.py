# START/startBD.py
from __future__ import annotations

import sys
from datetime import datetime

import pandas as pd

from config.paths import SCHEMA_PATH, CSV_PATH
from data.BD.connection import get_conn

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg: str):
    print(f"[{now()}] {msg}")

def criar_schema(conn):
    log("🧱 Criando/validando schema do banco...")
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    log("✅ Schema OK")

def importar_csv_sem_duplicar(conn, csv_path):
    log(f"📥 Lendo CSV: {csv_path}")
    df = pd.read_csv(csv_path, sep=";")

    # Esperado: col0=concurso, col1..col15 = dezenas
    concursos_csv = []
    for _, row in df.iterrows():
        concurso = int(row.iloc[0])
        dezenas = [int(row.iloc[i]) for i in range(1, 16)]
        concursos_csv.append((concurso, dezenas))

    log(f"📌 CSV carregado: {len(concursos_csv)} concursos")

    cur = conn.cursor()

    # Inserção incremental sem duplicar
    log("🗄️ Inserindo concursos (sem duplicar)...")
    inseridos = 0
    for concurso, dezenas in concursos_csv:
        cur.execute(
            """
            INSERT OR IGNORE INTO concursos (
                concurso,d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [concurso] + dezenas
        )
        inseridos += cur.rowcount

    conn.commit()
    log(f"✅ Inseridos: {inseridos} (ignorados duplicados: {len(concursos_csv)-inseridos})")

    # Recalcula frequencias (leve e rápido)
    log("📊 Recalculando tabela 'frequencias'...")
    cur.execute("DELETE FROM frequencias")
    contagem = {i: 0 for i in range(1, 26)}

    # Buscar do banco (fonte)
    cur.execute("SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15 FROM concursos")
    rows = cur.fetchall()
    for r in rows:
        for dez in r:
            contagem[int(dez)] += 1

    total = sum(contagem.values())
    for numero, qtd in contagem.items():
        peso = qtd / total if total else 0.0
        cur.execute(
            "INSERT INTO frequencias (numero, quantidade, peso, atualizado_em) VALUES (?,?,?,?)",
            (numero, qtd, peso, now())
        )
    conn.commit()
    log("✅ Frequências atualizadas")

def main():
    try:
        conn = get_conn()
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
