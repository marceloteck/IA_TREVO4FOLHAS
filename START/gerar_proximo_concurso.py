from __future__ import annotations

import argparse
import sys
import sqlite3
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ==========================
# Boot de path (roda de qualquer lugar)
# ==========================
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from config.paths import DB_PATH
except Exception:
    DB_PATH = ROOT / "data" / "BD" / "lotofacil.db"

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub


# ==========================
# Util
# ==========================
UNIVERSO = list(range(1, 26))


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}")


def contar_acertos(a: List[int], b: List[int]) -> int:
    return len(set(a) & set(b))


def jaccard(a: List[int], b: List[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def count_even(jogo: List[int]) -> int:
    return sum(1 for x in jogo if x % 2 == 0)


def max_consecutive_run(jogo: List[int]) -> int:
    s = sorted(jogo)
    best = cur = 1
    for i in range(1, len(s)):
        if s[i] == s[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


# ==========================
# DB (contexto e memória)
# ==========================
def fetch_max_concurso(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT MAX(concurso) FROM concursos")
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def fetch_result(conn, concurso: int) -> Optional[List[int]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        WHERE concurso=?
        """,
        (int(concurso),),
    )
    row = cur.fetchone()
    if not row:
        return None
    return [int(x) for x in row]


def fetch_recent_results(conn, concurso_n: int, janela: int) -> List[List[int]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        WHERE concurso <= ?
        ORDER BY concurso DESC
        LIMIT ?
        """,
        (int(concurso_n), int(janela)),
    )
    rows = cur.fetchall()
    rows = list(reversed(rows))
    return [[int(x) for x in r] for r in rows]


def build_context(conn, concurso_n: int, janela_recente: int) -> Dict[str, Any]:
    historico = fetch_recent_results(conn, concurso_n, janela_recente)
    ultimo = historico[-1] if historico else (fetch_result(conn, concurso_n) or [])
    freq: Dict[int, int] = {i: 0 for i in range(1, 26)}
    for r in historico:
        for d in r:
            freq[int(d)] += 1

    return {
        "concurso_n": int(concurso_n),
        "ultimo_resultado": [int(x) for x in ultimo],
        "historico_recente": historico,
        "freq_recente": freq,
        "janela_recente": int(janela_recente),
    }


def fetch_memoria_top(conn, min_pontos: int = 14, limit: int = 400) -> List[List[int]]:
    """
    Pega jogos fortes (>= min_pontos) recentes para medir similaridade (memória).
    """
    if not safe_table_exists(conn, "memoria_jogos"):
        return []

    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18
        FROM memoria_jogos
        WHERE acertos >= ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (int(min_pontos), int(limit)),
    )
    rows = cur.fetchall()
    jogos: List[List[int]] = []
    for r in rows:
        nums = [int(x) for x in r if x is not None]
        if len(nums) >= 15:
            jogos.append(sorted(nums))
    return jogos


# ==========================
# Registro de cérebros (auto)
# ==========================
def register_brains_auto(conn, hub: BrainHub) -> List[str]:
    """
    Registra todos os brains que existirem no seu projeto.
    Se um import falhar, ele só pula (sem quebrar).
    """
    loaded: List[str] = []

    def _try_add(import_path: str, cls_name: str, *args, **kwargs):
        nonlocal loaded
        try:
            mod = __import__(import_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            b = cls(conn, *args, **kwargs)
            hub.register(b)
            loaded.append(getattr(b, "id", f"{import_path}.{cls_name}"))
        except Exception:
            # silencioso (pra não travar seu fluxo)
            pass

    # Base (confirmados)
    _try_add("training.brains.statistical.freq_global_brain", "StatFreqGlobalBrain")
    _try_add("training.brains.statistical.freq_recente_brain", "StatFreqRecenteBrain", janela=120)
    _try_add("training.brains.temporal.atraso_brain", "TemporalAtrasoBrain")

    # Extras (se existirem)
    _try_add("training.brains.statistical.nucleo_satelites_brain", "StatNucleoSatelitesBrain")
    _try_add("training.brains.exploratory.total_dezenas_auto_brain", "ExplorTotalDezenasAutoBrain")
    _try_add("training.brains.statistical.elite_memory_brain", "StatEliteMemoryBrain")
    _try_add("training.brains.statistical.paridade_faixas_brain", "StatParidadeFaixasBrain")
    _try_add("training.brains.structural.pattern_shape_brain", "StructuralPatternShapeBrain")

    return loaded


# ==========================
# Scoring final (profissional e explicável)
# ==========================
def score_freq_recente(jogo: List[int], freq: Dict[int, int]) -> float:
    if not jogo:
        return 0.0
    maxf = max(freq.values()) if freq else 1
    if maxf <= 0:
        return 0.0
    return sum(freq.get(int(d), 0) / maxf for d in jogo) / len(jogo)


def score_shape(jogo: List[int], size: int) -> float:
    """
    Heurística leve de “formato” (não é regra, é só priorização):
    - pares dentro de faixa razoável
    - sem sequência gigante
    """
    if not jogo:
        return 0.0

    ev = count_even(jogo)
    run = max_consecutive_run(jogo)

    # Faixas típicas (leve)
    if size == 15:
        # pares geralmente 6..9 é ok
        pares_ok = 1.0 if 6 <= ev <= 9 else 0.6
        run_ok = 1.0 if run <= 4 else 0.6
    else:
        pares_ok = 1.0 if 7 <= ev <= 11 else 0.6
        run_ok = 1.0 if run <= 5 else 0.6

    return 0.5 * pares_ok + 0.5 * run_ok


def score_memoria(jogo: List[int], memoria: List[List[int]]) -> float:
    """
    Não é “copiar memória”, é medir se o candidato é parecido
    com padrões que já deram 14/15 no passado (normaliza 0..1).
    """
    if not memoria:
        return 0.0
    best = 0.0
    for m in memoria[:200]:
        best = max(best, jaccard(jogo, m))
    return best


def diversify_ranked(items: List[Dict[str, Any]], top_k: int, max_sim: float) -> List[Dict[str, Any]]:
    chosen: List[Dict[str, Any]] = []
    for it in items:
        jogo = it["jogo"]
        ok = True
        for c in chosen:
            if jaccard(jogo, c["jogo"]) >= max_sim:
                ok = False
                break
        if ok:
            chosen.append(it)
        if len(chosen) >= top_k:
            break
    return chosen


# ==========================
# MAIN
# ==========================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gerar jogos para o próximo concurso usando BrainHub + memória + contexto."
    )
    parser.add_argument("--size", type=int, default=15, help="Tamanho do jogo (15 ou 18).")
    parser.add_argument("--qtd", type=int, default=10, help="Quantidade de jogos finais para imprimir/salvar.")
    parser.add_argument("--janela", type=int, default=300, help="Janela de histórico para contexto.")
    parser.add_argument("--per-brain", type=int, default=120, help="Candidatos por cérebro.")
    parser.add_argument("--top-n", type=int, default=250, help="Top candidatos após BrainHub (antes do re-ranking).")
    parser.add_argument("--max-sim", type=float, default=0.78, help="Diversidade (Jaccard máximo entre jogos finais).")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade (opcional).")
    args = parser.parse_args()

    size = int(args.size)
    if size not in (15, 18):
        size = 15

    qtd = max(1, int(args.qtd))
    janela = max(50, int(args.janela))
    per_brain = max(10, int(args.per_brain))
    top_n = max(qtd, int(args.top_n))
    max_sim = float(args.max_sim)

    if args.seed is not None:
        random.seed(int(args.seed))

    db_path = Path(DB_PATH)
    if not db_path.exists():
        log(f"❌ DB não encontrado em: {db_path}")
        log("Rode primeiro: python START\\startBD.py")
        return

    conn = get_conn()
    try:
        if not safe_table_exists(conn, "concursos"):
            log("❌ Tabela 'concursos' não existe. Rode START/startBD.py.")
            return

        ultimo_concurso = fetch_max_concurso(conn)
        if ultimo_concurso < 1:
            log("❌ Sem concursos no banco. Importe o CSV e rode START/startBD.py.")
            return

        proximo_concurso = ultimo_concurso + 1
        log("=========================================")
        log("🎯 GERADOR — PRÓXIMO CONCURSO (BrainHub)")
        log("=========================================")
        log(f"📌 Último concurso no DB : {ultimo_concurso}")
        log(f"📌 Próximo concurso      : {proximo_concurso}")
        log(f"📌 Tamanho do jogo       : {size}")
        log(f"📌 Qtd jogos finais      : {qtd}")
        log("=========================================")

        context = build_context(conn, concurso_n=ultimo_concurso, janela_recente=janela)
        freq = context.get("freq_recente", {}) or {}
        memoria_1415 = fetch_memoria_top(conn, min_pontos=14, limit=500)

        hub = BrainHub(conn)
        loaded = register_brains_auto(conn, hub)

        if not loaded:
            log("❌ Nenhum cérebro foi carregado. Verifique seus imports/pastas 'training/brains'.")
            return

        hub.load_all()  # carrega estado persistido dos cérebros
        log(f"🧠 Cérebros ativos carregados: {len(loaded)}")

        # 1) Candidatos do hub (já com diversidade inicial)
        candidatos = hub.generate_games(
            context=context,
            size=size,
            per_brain=per_brain,
            top_n=top_n,
        )

        if not candidatos:
            log("❌ Hub não gerou candidatos (verifique cérebros/estado).")
            return

        # 2) Re-ranking final: score do hub + freq recente + memória + shape
        ranked: List[Dict[str, Any]] = []
        for c in candidatos:
            jogo = [int(x) for x in c["jogo"]]
            s_hub = float(c.get("score", 0.0))
            s_freq = score_freq_recente(jogo, freq)
            s_mem = score_memoria(jogo, memoria_1415)
            s_shape = score_shape(jogo, size)

            # pesos (pode ajustar depois sem quebrar nada)
            score_final = (
                0.55 * s_hub +
                0.20 * s_freq +
                0.15 * s_mem +
                0.10 * s_shape
            )

            ranked.append({
                "jogo": sorted(jogo),
                "score_final": float(score_final),
                "score_hub": float(s_hub),
                "score_freq": float(s_freq),
                "score_mem": float(s_mem),
                "score_shape": float(s_shape),
                "brain_id": str(c.get("brain_id", "unknown")),
            })

        ranked.sort(key=lambda x: x["score_final"], reverse=True)

        # 3) Diversidade final (evita jogos quase iguais)
        final = diversify_ranked(ranked, top_k=qtd, max_sim=max_sim)

        # 4) Saída + salvar em TXT
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_path = reports_dir / f"proximo_concurso_{proximo_concurso}_jogos_{size}.txt"

        lines: List[str] = []
        lines.append("=========================================")
        lines.append("🎯 JOGOS SUGERIDOS — PRÓXIMO CONCURSO")
        lines.append("=========================================")
        lines.append(f"Data/Hora: {now_str()}")
        lines.append(f"Último concurso conhecido: {ultimo_concurso}")
        lines.append(f"Próximo concurso: {proximo_concurso}")
        lines.append(f"Tamanho do jogo: {size}")
        lines.append(f"Cérebros ativos: {len(loaded)}")
        lines.append(f"Janela (contexto): {janela}")
        lines.append(f"Candidatos por cérebro: {per_brain}")
        lines.append(f"Diversidade max_sim (Jaccard): {max_sim}")
        lines.append("=========================================\n")

        print("\n✅ Jogos finais (priorizados):\n")
        for i, item in enumerate(final, 1):
            jogo = item["jogo"]
            s = item["score_final"]
            # exibe simples (sem “prometer” nada)
            print(f"JOGO {i:02d}: {jogo} | score={s:.4f} | fonte={item['brain_id']}")

            lines.append(f"JOGO {i:02d}: {jogo}")
            lines.append(
                f"  score_final={item['score_final']:.6f} | hub={item['score_hub']:.6f} | "
                f"freq={item['score_freq']:.6f} | mem={item['score_mem']:.6f} | shape={item['score_shape']:.6f} | "
                f"fonte={item['brain_id']}"
            )
            lines.append("")

        # dica operacional
        lines.append("Observação importante:")
        lines.append("- Loteria é aleatória. Este ranking só prioriza candidatos segundo o aprendizado do sistema.")
        lines.append("- Use com responsabilidade e dentro do seu orçamento.")
        lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        log(f"📄 Relatório salvo em: {out_path}")

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
