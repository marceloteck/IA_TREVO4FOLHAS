import sqlite3
import pandas as pd
import json
from pathlib import Path
from datetime import datetime

from config.paths import DB_PATH, SCHEMA_PATH, CSV_PATH

# ==========================
# UTIL
# ==========================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ==========================
# START
# ==========================
def start_bd():
    try:
        # --------------------------
        # 1. CRIAR BANCO
        # --------------------------
        log("Criando banco de dados...")
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # --------------------------
        # 2. CRIAR TABELAS
        # --------------------------
        log("Criando tabelas (schema)...")
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            cursor.executescript(f.read())

        # --------------------------
        # 3. IMPORTAR CSV
        # --------------------------
        log("Lendo CSV da Lotofácil...")
        df = pd.read_csv(CSV_PATH, sep=";")

        log("Limpando concursos antigos...")
        cursor.execute("DELETE FROM concursos")

        log("Inserindo concursos...")
        for _, row in df.iterrows():
            concurso = int(row.iloc[0])
            dezenas = ",".join(str(int(d)).zfill(2) for d in row.iloc[1:16])

            cursor.execute("""
                INSERT OR IGNORE INTO concursos (concurso, dezenas, data)
                VALUES (?, ?, ?)
            """, (concurso, dezenas, None))

        # --------------------------
        # 4. CALCULAR FREQUÊNCIAS
        # --------------------------
        log("Calculando frequências globais...")
        contagem = {i: 0 for i in range(1, 26)}

        for _, row in df.iterrows():
            for dez in row.iloc[1:16]:
                contagem[int(dez)] += 1

        total = sum(contagem.values())

        frequencias = {
            str(num): {
                "quantidade": qtd,
                "peso": qtd / total
            }
            for num, qtd in contagem.items()
        }

        # --------------------------
        # 5. SALVAR ESTATÍSTICAS
        # --------------------------
        log("Salvando estatísticas consolidadas...")
        cursor.execute("""
            INSERT OR REPLACE INTO estatisticas (chave, valor, ultima_atualizacao)
            VALUES (?, ?, ?)
        """, (
            "frequencia_global",
            json.dumps(frequencias),
            datetime.now().isoformat()
        ))

        # --------------------------
        # 6. CHECKPOINT INICIAL
        # --------------------------
        log("Criando checkpoint inicial...")
        ultimo_concurso = int(df.iloc[-1, 0])

        cursor.execute("""
            INSERT OR REPLACE INTO checkpoint (id, ultimo_concurso_processado, ultimo_treino, timestamp)
            VALUES (1, ?, ?, ?)
        """, (
            ultimo_concurso,
            "bootstrap",
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        log("✅ Banco de dados pronto para uso!")
        log("Sistema inicializado com sucesso.")

    except Exception as e:
        log("❌ ERRO DURANTE A INICIALIZAÇÃO DO BANCO")
        log(str(e))

# ==========================
# EXEC
# ==========================
if __name__ == "__main__":
    start_bd()
