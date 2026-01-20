# START/update_concursos.py
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


# ----------------------------
# Path bootstrap (resolve "No module named config")
# ----------------------------
def find_project_root(start: Path) -> Path:
    """
    Sobe diretórios até encontrar indícios da raiz do projeto
    (pastas 'config' e 'data', ou um 'pyproject.toml', etc.).
    """
    cur = start.resolve()
    for _ in range(12):
        if (cur / "config").is_dir() and (cur / "data").is_dir():
            return cur
        if (cur / "pyproject.toml").exists() or (cur / "setup.cfg").exists() or (cur / ".git").exists():
            # ajuda quando config/data estão organizados diferente
            return cur
        cur = cur.parent
    return start.resolve()


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = find_project_root(THIS_FILE.parent)

# garante que a raiz do projeto esteja no sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ----------------------------
# Imports do projeto (agora funcionam)
# ----------------------------
def safe_import_paths():
    """
    Tenta importar CSV_PATH do config.paths.
    Se não existir, retorna None e seguimos com fallback.
    """
    try:
        from config.paths import CSV_PATH  # type: ignore
        return CSV_PATH
    except Exception:
        return None


def safe_import_conn():
    """
    Importa conexão do seu projeto.
    Ajuste aqui se o caminho do connection for diferente.
    """
    try:
        from data.BD.connection import get_conn  # type: ignore
        return get_conn
    except ModuleNotFoundError as e:
        raise ModuleNotFoundError(
            "Não encontrei 'data.BD.connection'. Confirme se existe esse arquivo/caminho no projeto.\n"
            f"Raiz detectada: {PROJECT_ROOT}\n"
            "Ex.: data/BD/connection.py (com get_conn())"
        ) from e


# ----------------------------
# Utils
# ----------------------------
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{now()}] {msg}")


def guess_csv_path(root: Path) -> Path | None:
    """
    Procura um CSV em locais comuns do projeto, se CSV_PATH não existir.
    Ajuste os nomes se você usa outro padrão.
    """
    candidates = [
        root / "data" / "Lotofacil.csv",
        root / "data" / "lotofacil.csv",
        root / "data" / "concursos.csv",
        root / "Lotofacil.csv",
        root / "concursos.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def ensure_tables_exist(cur):
    """
    Se você quiser criar automaticamente as tabelas quando não existirem,
    descomente o SQL abaixo.
    """
    # cur.execute("""
    # CREATE TABLE IF NOT EXISTS concursos (
    #   concurso INTEGER PRIMARY KEY,
    #   d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
    #   d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
    #   d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER
    # )
    # """)
    # cur.execute("""
    # CREATE TABLE IF NOT EXISTS frequencias (
    #   numero INTEGER PRIMARY KEY,
    #   quantidade INTEGER NOT NULL,
    #   peso REAL NOT NULL,
    #   atualizado_em TEXT NOT NULL
    # )
    # """)
    pass


def main():
    conn = None
    try:
        # 1) Resolve CSV_PATH
        cfg_csv_path = safe_import_paths()
        csv_path = cfg_csv_path if cfg_csv_path is not None else guess_csv_path(PROJECT_ROOT)

        if csv_path is None:
            log("❌ CSV_PATH não encontrado no config e nenhum CSV foi localizado por fallback.")
            log(f"   Raiz detectada: {PROJECT_ROOT}")
            log("   Dica: crie config/paths.py com CSV_PATH, ou coloque o CSV em data/Lotofacil.csv")
            sys.exit(1)

        csv_path = Path(csv_path)
        if not csv_path.exists():
            log(f"❌ CSV não encontrado: {csv_path}")
            sys.exit(1)

        # 2) Conexão DB
        get_conn = safe_import_conn()
        conn = get_conn()
        cur = conn.cursor()

        ensure_tables_exist(cur)

        log(f"📥 Lendo CSV: {csv_path}")
        # tenta ; primeiro (seu padrão), se falhar tenta autodetectar
        try:
            df = pd.read_csv(csv_path, sep=";")
        except Exception:
            df = pd.read_csv(csv_path, sep=None, engine="python")

        if df.shape[1] < 16:
            raise ValueError(f"CSV com colunas insuficientes. Esperado 16+ (concurso + 15 dezenas). Veio: {df.shape[1]}")

        # 3) Maior concurso no DB
        cur.execute("SELECT MAX(concurso) FROM concursos")
        row = cur.fetchone()
        max_db = int(row[0]) if row and row[0] is not None else 0
        log(f"📌 Maior concurso no DB: {max_db}")

        # 4) Inserção de novos concursos
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
            # no sqlite, rowcount pode ser 0 quando IGNORE; ainda assim é ok
            if cur.rowcount and cur.rowcount > 0:
                novos += cur.rowcount

        conn.commit()
        log(f"✅ Novos concursos inseridos: {novos}")

        # 5) Atualizar frequências
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
            peso = (qtd / total) if total else 0.0
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
            if conn:
                conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
