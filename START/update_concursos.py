# START/update_concursos.py
from __future__ import annotations

import sys
from datetime import datetime

import pandas as pd

from config.paths import CSV_PATH
from data.BD.connection import get_conn

def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log(msg: str):
    print(f"[{now()}] {msg}")

def main():
    try:
        if not CSV_PATH.exists():
            log(f"❌ CSV não encontrado: {CSV_PATH}")
            sys.exit(1)

        conn = get_conn()
        cur = conn.cursor()

        log("📥 Lendo CSV...")
        df = pd.read_csv(CSV_PATH, sep=";")

        # Descobre o maior concurso já no banco
        cur.execute("SELECT MAX(concurso) FROM concursos")
        row = cur.fetchone()
        max_db = int(row[0]) if row and row[0] is not None else 0

        log(f"📌 Maior concurso no DB: {max_db}")

        novos = 0
        for _, r in df.iterrows():
            concurso = int(r.iloc[0])
            if concurso <= max_db:
                continue
            dezenas = [int(r.iloc[i]) for i in range(1, 16)]
            cur.execute(
                """
                INSERT OR IGNORE INTO concursos (
                    concurso,d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                [concurso] + dezenas
            )
            novos += cur.rowcount

        conn.commit()
        log(f"✅ Novos concursos inseridos: {novos}")

        log("📊 Atualizando frequencias...")
        cur.execute("DELETE FROM frequencias")
        contagem = {i: 0 for i in range(1, 26)}
        cur.execute("SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15 FROM concursos")
        rows = cur.fetchall()
        for rr in rows:
            for dez in rr:
                contagem[int(dez)] += 1

        total = sum(contagem.values())
        for numero, qtd in contagem.items():
            peso = qtd / total if total else 0.0
            cur.execute(
                "INSERT INTO frequencias (numero, quantidade, peso, atualizado_em) VALUES (?,?,?,?)",
                (numero, qtd, peso, now())
            )
        conn.commit()
        log("✅ Frequencias atualizadas")

        log("🎉 Atualização concluída")
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
