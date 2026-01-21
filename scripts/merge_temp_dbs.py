from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
TEMP_DIR = ROOT / "data" / "BD" / "temp"
MAIN_DB = ROOT / "data" / "BD" / "lotofacil.db"

# regra: só importar memoria_jogos 14+
MIN_ACERTOS = 14


def table_exists_attached(conn: sqlite3.Connection, schema: str, name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def safe_detach(conn: sqlite3.Connection, schema: str = "tdb") -> None:
    try:
        conn.execute(f"DETACH DATABASE {schema}")
    except Exception:
        pass


def attach_temp_db(main_conn: sqlite3.Connection, temp_db: Path) -> None:
    safe_detach(main_conn, "tdb")

    # URI correto no Windows + read-only
    uri = temp_db.resolve().as_uri() + "?mode=ro"
    try:
        main_conn.execute("ATTACH DATABASE ? AS tdb", (uri,))
        return
    except sqlite3.OperationalError:
        safe_detach(main_conn, "tdb")
        main_conn.execute("ATTACH DATABASE ? AS tdb", (str(temp_db),))


def merge_one(temp_db: Path, main_conn: sqlite3.Connection) -> bool:
    attach_temp_db(main_conn, temp_db)

    try:
        if not table_exists_attached(main_conn, "tdb", "memoria_jogos"):
            return False

        with main_conn:
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

            if table_exists_attached(main_conn, "tdb", "predicoes_proximo"):
                main_conn.execute(
                    """
                    INSERT OR IGNORE INTO predicoes_proximo
                    SELECT * FROM tdb.predicoes_proximo
                    """
                )

        return True

    finally:
        try:
            main_conn.execute("DETACH DATABASE tdb")
        except sqlite3.OperationalError:
            try:
                main_conn.commit()
            except Exception:
                pass
            safe_detach(main_conn, "tdb")


def integrity_check(conn: sqlite3.Connection) -> tuple[bool, str]:
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    rows = cur.fetchall()
    msg = "\n".join(r[0] for r in rows if r and r[0] is not None)
    ok = (msg.strip().lower() == "ok")
    return ok, msg


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(path.stem + f"_BACKUP_{ts}" + path.suffix)
    backup.write_bytes(path.read_bytes())
    return backup


def recover_database_built_in(main_db: Path) -> Path:
    """
    Recuperação via sqlite3.Connection.iterdump()
    (não recupera 100% em casos extremos, mas resolve muitos cenários)
    """
    recovered = main_db.with_name(main_db.stem + "_recovered" + main_db.suffix)

    # abre origem e destino
    src = sqlite3.connect(str(main_db))
    try:
        # evita travas durante dump
        src.execute("PRAGMA busy_timeout=15000;")
        dump_sql = "\n".join(src.iterdump())
    finally:
        src.close()

    dst = sqlite3.connect(str(recovered))
    try:
        dst.execute("PRAGMA journal_mode=WAL;")
        dst.executescript(dump_sql)
        dst.commit()
    finally:
        dst.close()

    return recovered


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
        main_conn.execute("PRAGMA busy_timeout = 15000;")
        main_conn.execute("PRAGMA journal_mode=WAL;")
        main_conn.execute("PRAGMA synchronous=NORMAL;")

        merged = 0
        failed = 0

        for db in dbs:
            print(f"🔄 Mesclando: {db}")
            try:
                processed = merge_one(db, main_conn)
                # apaga após sucesso
                db.unlink(missing_ok=True)
                merged += 1
            except Exception as e:
                failed += 1
                print(f"❌ Falhou ao mesclar {db.name}: {e}")

        print(f"✅ Mesclagem concluída. DBs processados: {merged} | falhas: {failed}")

        # ✅ Antes de VACUUM, checa integridade
        print("🔎 Verificando integridade do MAIN_DB...")
        ok, msg = integrity_check(main_conn)
        if ok:
            print("✅ integrity_check: OK")
            print("🧹 Rodando VACUUM… (pode demorar)")
            try:
                main_conn.execute("VACUUM;")
                main_conn.commit()
                print("✅ VACUUM OK")
            except sqlite3.DatabaseError as e:
                print(f"⚠️ VACUUM falhou: {e}")
                print("➡️ Pulei o VACUUM (DB pode estar com problema físico).")
        else:
            print("❌ integrity_check detectou problemas:")
            print(msg)

            print("📦 Fazendo backup do MAIN_DB antes de tentar recuperar...")
            bkp = backup_file(MAIN_DB)
            print(f"✅ Backup criado em: {bkp}")

            print("🛠️ Tentando recuperar para um novo arquivo...")
            try:
                recovered = recover_database_built_in(MAIN_DB)
                print(f"✅ Recuperado em: {recovered}")
                print("➡️ Agora você pode substituir manualmente lotofacil.db pelo lotofacil_recovered.db")
            except Exception as e:
                print(f"❌ Falha na recuperação automática: {e}")
                print("➡️ Próximo passo: usar o comando sqlite3 .recover (te explico se precisar).")

    finally:
        main_conn.close()


if __name__ == "__main__":
    main()
