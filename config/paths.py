from pathlib import Path

# Raiz do projeto (ajusta automaticamente)
BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# BANCO DE DADOS
# =========================
DB_DIR = BASE_DIR / "data" / "BD"
DB_PATH = DB_DIR / "lotofacil.db"

# =========================
# SCHEMA
# =========================
SCHEMA_PATH = BASE_DIR / "data" / "database" / "db_schema.sql"

# =========================
# CSV / PLANILHAS
# =========================
CSV_PATH = BASE_DIR / "data" / "planilhas" / "Lotofácil.csv"
