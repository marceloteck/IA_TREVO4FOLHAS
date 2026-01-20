# START/status_aprendizado.py
from __future__ import annotations

import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ==========================
# Boot de path (roda de qualquer lugar)
# ==========================
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from config.paths import DB_PATH
except Exception:
    # fallback seguro
    DB_PATH = ROOT / "data" / "BD" / "lotofacil.db"


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fmt_int(n: Optional[int]) -> str:
    if n is None:
        return "-"
    return f"{int(n):,}".replace(",", ".")


def fmt_float(x: Optional[float], nd: int = 2) -> str:
    if x is None:
        return "-"
    return f"{float(x):.{nd}f}"


def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def safe_col_exists(conn: sqlite3.Connection, table: str, col: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        return col in cols
    except Exception:
        return False


def get_conn() -> sqlite3.Connection:
    db_path = Path(DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ==========================
# Queries (resumo geral)
# ==========================
def q_one(conn: sqlite3.Connection, sql: str, params: Tuple = ()) -> Optional[Tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchone()


def q_all(conn: sqlite3.Connection, sql: str, params: Tuple = ()) -> List[Tuple]:
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> None:
    print_header("🧠 STATUS DE APRENDIZADO — IA_TREVO4FOLHAS (DB)")

    db_path = Path(DB_PATH)
    print(f"[{now_str()}] 📌 DB: {db_path}")

    if not db_path.exists():
        print("\n❌ Banco não encontrado. Rode primeiro:")
        print("   python START\\startBD.py")
        print("   (e/ou START\\update_concursos.py)")
        return

    conn = get_conn()
    try:
        # Checagem mínima
        needed = ["concursos", "checkpoint", "tentativas", "memoria_jogos", "cerebros", "cerebro_estado", "cerebro_performance"]
        missing = [t for t in needed if not safe_table_exists(conn, t)]
        if missing:
            print("\n❌ Tabelas faltando no banco:", ", ".join(missing))
            print("   Rode: python START\\startBD.py (para criar schema completo)")
            return

        # --------------------------
        # 1) Fonte de dados (concursos)
        # --------------------------
        print_header("1) BASE OFICIAL (CONCURSOS)")
        total_concursos = q_one(conn, "SELECT COUNT(*) FROM concursos")
        min_conc = q_one(conn, "SELECT MIN(concurso) FROM concursos")
        max_conc = q_one(conn, "SELECT MAX(concurso) FROM concursos")
        print(f"Total de concursos no DB: {fmt_int(total_concursos[0] if total_concursos else 0)}")
        print(f"Faixa: {fmt_int(min_conc[0] if min_conc else None)} .. {fmt_int(max_conc[0] if max_conc else None)}")

        # --------------------------
        # 2) Checkpoint e progresso incremental
        # --------------------------
        print_header("2) CHECKPOINT (TREINO INCREMENTAL)")
        ck = q_one(conn, "SELECT ultimo_concurso_processado, etapa, timestamp FROM checkpoint WHERE id=1")
        if ck:
            ultimo = ck[0]
            etapa = ck[1]
            ts = ck[2]
            print(f"Último concurso treinado (N): {fmt_int(ultimo)}")
            print(f"Etapa: {etapa or '-'}")
            print(f"Atualizado em: {ts or '-'}")

            # progresso estimado (precisa existir N+1)
            max_treino = (max_conc[0] - 1) if max_conc and max_conc[0] else None
            if max_treino is not None:
                faltam = max(0, int(max_treino) - int(ultimo or 0))
                print(f"Máximo treinável hoje (penúltimo): {fmt_int(max_treino)}")
                print(f"Pendentes para treinar: {fmt_int(faltam)}")
        else:
            print("Checkpoint não encontrado (ainda não treinou).")

        # --------------------------
        # 3) Tentativas (histórico de treino)
        # --------------------------
        print_header("3) TENTATIVAS (HISTÓRICO DO TREINO)")
        tent_total = q_one(conn, "SELECT COUNT(*) FROM tentativas")
        tent_range = q_one(conn, "SELECT MIN(concurso_n), MAX(concurso_n) FROM tentativas")
        print(f"Total de tentativas registradas: {fmt_int(tent_total[0] if tent_total else 0)}")
        if tent_range and (tent_range[0] is not None or tent_range[1] is not None):
            print(f"Faixa de concursos treinados (N): {fmt_int(tent_range[0])} .. {fmt_int(tent_range[1])}")

        # melhores acertos já vistos (15/18)
        best15 = q_one(conn, "SELECT MAX(acertos) FROM tentativas WHERE tipo_jogo=15")
        best18 = q_one(conn, "SELECT MAX(acertos) FROM tentativas WHERE tipo_jogo=18")
        print(f"Melhor acerto já visto (jogo 15): {fmt_int(best15[0] if best15 else None)}")
        print(f"Melhor acerto já visto (jogo 18): {fmt_int(best18[0] if best18 else None)}")

        # distribuição de acertos (top)
        dist = q_all(
            conn,
            """
            SELECT tipo_jogo, acertos, COUNT(*)
            FROM tentativas
            GROUP BY tipo_jogo, acertos
            ORDER BY tipo_jogo ASC, acertos DESC
            """
        )
        if dist:
            print("\nDistribuição (tipo_jogo, acertos -> qtd):")
            last_tipo = None
            for tipo, ac, qtd in dist:
                if last_tipo != tipo:
                    print(f"\n  Tipo {tipo}:")
                    last_tipo = tipo
                print(f"    {fmt_int(ac)} pts -> {fmt_int(qtd)}")

        # --------------------------
        # 4) Memória forte (>=11)
        # --------------------------
        print_header("4) MEMÓRIA FORTE (memoria_jogos)")
        mem_total = q_one(conn, "SELECT COUNT(*) FROM memoria_jogos")
        mem_range = q_one(conn, "SELECT MIN(concurso_n), MAX(concurso_n) FROM memoria_jogos")
        print(f"Total na memória forte: {fmt_int(mem_total[0] if mem_total else 0)}")
        if mem_range and (mem_range[0] is not None or mem_range[1] is not None):
            print(f"Faixa de concursos (N) na memória: {fmt_int(mem_range[0])} .. {fmt_int(mem_range[1])}")

        mem_dist = q_all(
            conn,
            """
            SELECT tipo_jogo, acertos, COUNT(*)
            FROM memoria_jogos
            GROUP BY tipo_jogo, acertos
            ORDER BY tipo_jogo ASC, acertos DESC
            """
        )
        if mem_dist:
            print("\nDistribuição memória (tipo_jogo, acertos -> qtd):")
            last_tipo = None
            for tipo, ac, qtd in mem_dist:
                if last_tipo != tipo:
                    print(f"\n  Tipo {tipo}:")
                    last_tipo = tipo
                print(f"    {fmt_int(ac)} pts -> {fmt_int(qtd)}")

        # --------------------------
        # 5) Cérebros registrados + estados
        # --------------------------
        print_header("5) CÉREBROS (REGISTRO + ESTADO)")
        cerebros_total = q_one(conn, "SELECT COUNT(*) FROM cerebros")
        cerebros_on = q_one(conn, "SELECT COUNT(*) FROM cerebros WHERE habilitado=1")
        print(f"Cérebros cadastrados: {fmt_int(cerebros_total[0] if cerebros_total else 0)}")
        print(f"Cérebros habilitados: {fmt_int(cerebros_on[0] if cerebros_on else 0)}")

        # estados salvos
        estado_total = q_one(conn, "SELECT COUNT(*) FROM cerebro_estado")
        print(f"Estados persistidos (cerebro_estado): {fmt_int(estado_total[0] if estado_total else 0)}")

        # lista rápida de cérebros
        rows = q_all(
            conn,
            """
            SELECT brain_id, nome, categoria, versao, habilitado, atualizado_em
            FROM cerebros
            ORDER BY categoria, brain_id
            """
        )
        if rows:
            print("\nLista de cérebros:")
            for brain_id, nome, cat, ver, hab, upd in rows:
                flag = "ON " if int(hab or 0) == 1 else "OFF"
                print(f"  [{flag}] {brain_id} | {cat} | v={ver} | {nome} | upd={upd or '-'}")

        # --------------------------
        # 6) Performance por cérebro (resumo)
        # --------------------------
        print_header("6) PERFORMANCE (cerebro_performance) — RESUMO")
        perf_exists = safe_table_exists(conn, "cerebro_performance")
        if perf_exists:
            # total de linhas
            perf_total = q_one(conn, "SELECT COUNT(*) FROM cerebro_performance")
            print(f"Linhas de performance: {fmt_int(perf_total[0] if perf_total else 0)}")

            # agregação por cérebro
            perf = q_all(
                conn,
                """
                SELECT c.brain_id,
                       SUM(p.jogos_gerados) AS jogos,
                       AVG(p.media_pontos) AS media,
                       SUM(p.qtd_11) AS q11,
                       SUM(p.qtd_12) AS q12,
                       SUM(p.qtd_13) AS q13,
                       SUM(p.qtd_14) AS q14,
                       SUM(p.qtd_15) AS q15
                FROM cerebro_performance p
                JOIN cerebros c ON c.id = p.cerebro_id
                GROUP BY c.brain_id
                ORDER BY q15 DESC, q14 DESC, media DESC
                LIMIT 30
                """
            )
            if perf:
                print("\nTop cérebros (ordenado por 15, 14, média):")
                for brain_id, jogos, media, q11, q12, q13, q14, q15 in perf:
                    print(
                        f"  {brain_id:35s} | jogos={fmt_int(jogos)} | média={fmt_float(media)}"
                        f" | 14+={fmt_int(q14)} | 15={fmt_int(q15)}"
                    )
            else:
                print("Sem dados de performance ainda (normal no começo).")
        else:
            print("Tabela cerebro_performance não existe (ok, mas recomendado no seu schema).")

        # --------------------------
        # 7) Frequências (sanidade)
        # --------------------------
        print_header("7) FREQUÊNCIAS (SANIDADE)")
        if safe_table_exists(conn, "frequencias"):
            fr = q_one(conn, "SELECT COUNT(*) FROM frequencias")
            print(f"Linhas em frequencias: {fmt_int(fr[0] if fr else 0)}")
            topf = q_all(conn, "SELECT numero, quantidade, peso FROM frequencias ORDER BY quantidade DESC LIMIT 10")
            if topf:
                print("Top 10 dezenas por frequência (histórico total):")
                for num, qtd, peso in topf:
                    print(f"  dezena {int(num):02d} -> qtd={fmt_int(qtd)} | peso={fmt_float(peso, 6)}")
        else:
            print("Tabela frequencias não existe. Rode START/startBD.py para criar/atualizar.")

        print("\n✅ Status concluído.")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
