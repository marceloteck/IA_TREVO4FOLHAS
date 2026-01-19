import sqlite3
import pandas as pd
from pathlib import Path
from datetime import datetime

from config.paths import DB_PATH, CSV_PATH

# ==========================
# UTIL
# ==========================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ==========================
# ATUALIZAR CONCURSOS
# ==========================
def atualizar_concursos():
    try:
        if not DB_PATH.exists():
            raise FileNotFoundError("Banco de dados não encontrado. Execute startBD.py primeiro.")

        log("Conectando ao banco de dados...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # --------------------------
        # 1. Último concurso salvo
        # --------------------------
        cursor.execute("SELECT MAX(concurso) FROM concursos")
        ultimo_concurso = cursor.fetchone()[0] or 0

        log(f"Último concurso no banco: {ultimo_concurso}")

        # --------------------------
        # 2. Ler CSV
        # --------------------------
        log("Lendo CSV atualizado...")
        df = pd.read_csv(CSV_PATH, sep=";")

        novos = df[df.iloc[:, 0] > ultimo_concurso]

        if novos.empty:
            log("Nenhum concurso novo encontrado.")
            conn.close()
            return

        log(f"{len(novos)} novos concursos encontrados.")

        # --------------------------
        # 3. Inserir novos concursos
        # --------------------------
        for _, row in novos.iterrows():
            concurso = int(row.iloc[0])
            dezenas = ",".join(str(int(d)).zfill(2) for d in row.iloc[1:16])

            cursor.execute("""
                INSERT OR IGNORE INTO concursos (concurso, dezenas, data)
                VALUES (?, ?, ?)
            """, (concurso, dezenas, None))

        # --------------------------
        # 4. Atualizar checkpoint
        # --------------------------
        ultimo_importado = int(novos.iloc[-1, 0])

        cursor.execute("""
            UPDATE checkpoint
            SET ultimo_concurso_processado = ?, 
                ultimo_treino = ?, 
                timestamp = ?
            WHERE id = 1
        """, (
            ultimo_importado,
            "import_csv_incremental",
            datetime.now().isoformat()
        ))

        conn.commit()
        conn.close()

        log(f"✅ Atualização concluída. Último concurso importado: {ultimo_importado}")

    except Exception as e:
        log("❌ ERRO NA ATUALIZAÇÃO DOS CONCURSOS")
        log(str(e))

# ==========================
# EXEC
# ==========================
if __name__ == "__main__":
    atualizar_concursos()
