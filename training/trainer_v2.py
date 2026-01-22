# training/trainer_v2.py
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import argparse
import time
import inspect
from datetime import datetime
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub
from training.utils.comparador import contar_acertos

# Cluster atual (adicione mais brains aqui depois)
from training.brains.statistical.freq_global_brain import StatFreqGlobalBrain
from training.brains.statistical.freq_recente_brain import StatFreqRecenteBrain
from training.brains.temporal.atraso_brain import TemporalAtrasoBrain
from training.brains.statistical.nucleo_satelites_brain import StatNucleoSatelitesBrain
from training.brains.exploratory.total_dezenas_auto_brain import ExplorTotalDezenasAutoBrain
from training.brains.statistical.elite_memory_brain import StatEliteMemoryBrain
from training.brains.statistical.paridade_faixas_brain import StatParidadeFaixasBrain
from training.brains.structural.pattern_shape_brain import StructuralPatternShapeBrain
from training.brains.heuristic.heuristic_brains import build_heuristic_brains
from training.brains.structural.core_protect_brain import StructuralCoreProtectBrain


# ==========================
# CONFIG (leve / i3 / 12GB)
# ==========================
JANELA_RECENTE = 300                 # base de contexto (histórico recente)
CANDIDATOS_POR_CEREBRO = 80          # candidatos por brain por tamanho
TOP_N_POR_TAMANHO = 60               # pós-hub (diversidade aplicada)
AVALIAR_TOP_K = 40                   # quantos avaliar por tamanho (custo controlado)
SALVAR_MEMORIA_MIN = 12              # salva memoria_jogos a partir de 11 acertos
PERSISTIR_A_CADA = 5                 # salva estados + checkpoint a cada X concursos
SCORE_TAG = "trainer_v2_hub"         # tag para auditoria


# ==========================
# COMMIT AUTOMATICO ACTIONS
# ==========================
def _try_commit_if_good_every(
    last_ts: float,
    interval_min: int = 30,
) -> float:
    """
    Tenta rodar scripts/commit_if_good.py de tempos em tempos.
    - Só faz sentido no GitHub Actions (GITHUB_ACTIONS=true).
    - Se falhar, não quebra o treinamento.
    Retorna o novo timestamp de referência.
    """
    if interval_min <= 0:
        return last_ts

    # Só roda no GitHub Actions (evita bagunçar máquina local)
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return last_ts

    now = time.time()
    if (now - last_ts) < (interval_min * 60):
        return last_ts

    try:
        root = Path(__file__).resolve().parents[1]  # raiz do repo
        script = root / "scripts" / "commit_if_good.py"
        if not script.exists():
            _log(f"⚠️ commit_if_good.py não encontrado em {script}")
            return now

        _log("🧾 Tentando commit automático (commit_if_good.py)...")
        # importante: roda com cwd na raiz do repo
        subprocess.run(
            [sys.executable, str(script)],
            cwd=str(root),
            check=False,
        )
    except Exception as e:
        _log(f"⚠️ Falha ao tentar commit automático: {e}")

    return now


# ==========================
# UTIL
# ==========================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{now_str()}] {msg}")


def _fetch_all_concursos(conn) -> List[int]:
    cur = conn.cursor()
    cur.execute("SELECT concurso FROM concursos ORDER BY concurso ASC")
    return [int(r[0]) for r in cur.fetchall()]


def _fetch_result(conn, concurso: int) -> Optional[List[int]]:
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


def _fetch_recent_results(conn, concurso_n: int, janela: int) -> List[List[int]]:
    """
    Retorna lista de resultados [ [15], [15], ... ] dos concursos <= concurso_n
    com tamanho máximo = janela (do mais antigo ao mais novo).
    """
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


def _get_checkpoint(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT ultimo_concurso_processado FROM checkpoint WHERE id=1")
    row = cur.fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


def _set_checkpoint(conn, ultimo_concurso: int, etapa: str = "trainer_v2") -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO checkpoint (id, ultimo_concurso_processado, etapa, timestamp)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ultimo_concurso_processado=excluded.ultimo_concurso_processado,
            etapa=excluded.etapa,
            timestamp=excluded.timestamp
        """,
        (int(ultimo_concurso), str(etapa), now_str()),
    )
    conn.commit()


def _insert_tentativa(
    conn,
    concurso_n: int,
    concurso_n1: int,
    tipo_jogo: int,
    tentativa: int,
    dezenas: List[int],
    acertos: int,
    score: float,
    brain_id: str,
    tempo_exec: float,
) -> None:
    """
    Insere em tentativas no formato d1..d18 (15 ou 18)
    (corrigido: placeholders automáticos -> nunca mais dá mismatch)
    """
    dezenas_sorted = sorted(int(x) for x in dezenas)
    payload = dezenas_sorted + [None] * (18 - len(dezenas_sorted))

    cols = [
        "concurso_n", "concurso_n1", "tipo_jogo", "tentativa",
        "d1","d2","d3","d4","d5","d6","d7","d8","d9","d10","d11","d12","d13","d14","d15","d16","d17","d18",
        "acertos", "score", "score_tag", "brain_id", "tempo_exec", "timestamp"
    ]

    values = [
        int(concurso_n),
        int(concurso_n1),
        int(tipo_jogo),
        int(tentativa),
        payload[0], payload[1], payload[2], payload[3], payload[4],
        payload[5], payload[6], payload[7], payload[8], payload[9],
        payload[10], payload[11], payload[12], payload[13], payload[14],
        payload[15], payload[16], payload[17],
        int(acertos),
        float(score),
        SCORE_TAG,
        str(brain_id),
        float(tempo_exec),
        now_str(),
    ]

    placeholders = ",".join(["?"] * len(values))
    sql = f"INSERT INTO tentativas ({','.join(cols)}) VALUES ({placeholders})"

    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()


def _insert_memoria_forte(
    conn,
    concurso_n: int,
    concurso_n1: int,
    tipo_jogo: int,
    dezenas: List[int],
    acertos: int,
    peso: float,
    origem: str,
) -> bool:
    """
    Salva memoria_jogos (>= SALVAR_MEMORIA_MIN) usando INSERT OR IGNORE
    (corrigido: placeholders automáticos)
    """
    if int(acertos) < int(SALVAR_MEMORIA_MIN):
        return False

    dezenas_sorted = sorted(int(x) for x in dezenas)
    payload = dezenas_sorted + [None] * (18 - len(dezenas_sorted))

    cols = [
        "concurso_n", "concurso_n1", "tipo_jogo",
        "d1","d2","d3","d4","d5","d6","d7","d8","d9","d10","d11","d12","d13","d14","d15","d16","d17","d18",
        "acertos", "peso", "origem", "timestamp"
    ]

    values = [
        int(concurso_n),
        int(concurso_n1),
        int(tipo_jogo),
        payload[0], payload[1], payload[2], payload[3], payload[4],
        payload[5], payload[6], payload[7], payload[8], payload[9],
        payload[10], payload[11], payload[12], payload[13], payload[14],
        payload[15], payload[16], payload[17],
        int(acertos),
        float(peso),
        str(origem),
        now_str(),
    ]

    placeholders = ",".join(["?"] * len(values))
    sql = f"INSERT OR IGNORE INTO memoria_jogos ({','.join(cols)}) VALUES ({placeholders})"

    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()
    return cur.rowcount > 0


def _build_context(conn, concurso_n: int, janela_recente: int) -> Dict[str, Any]:
    """
    Contexto canônico para todos os cérebros e para o Hub:
    - concurso_n
    - ultimo_resultado (N)
    - historico_recente (lista de resultados até N)
    - freq_recente (dict)
    """
    historico = _fetch_recent_results(conn, concurso_n=concurso_n, janela=janela_recente)
    ultimo = historico[-1] if historico else _fetch_result(conn, concurso_n) or []

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


def _rank_and_select(
    candidatos: List[Dict[str, Any]],
    resultado_n1: List[int],
    avaliar_top_k: int,
    tipo: int,
) -> List[Dict[str, Any]]:
    top = candidatos[: int(avaliar_top_k)]
    avaliados: List[Dict[str, Any]] = []
    for c in top:
        jogo = [int(x) for x in c["jogo"]]
        ac = contar_acertos(jogo, resultado_n1)
        avaliados.append(
            {
                "jogo": sorted(jogo),
                "acertos": int(ac),
                "score": float(c.get("score", 0.0)),
                "brain_id": str(c.get("brain_id", "unknown")),
                "tipo": int(tipo),
            }
        )
    avaliados.sort(key=lambda x: (x["acertos"], x["score"]), reverse=True)
    return avaliados


# =========================================================
# ✅ INSTANCIAÇÃO ROBUSTA DE CÉREBROS (RESOLVE SEU ERRO)
# =========================================================
def _instantiate_brain(brain_cls, conn, **kwargs):
    """
    Instancia qualquer cérebro de forma segura:
    - sempre passa conn
    - só passa kwargs que existirem no __init__
    - evita quebrar o trainer quando o cérebro não tem o argumento
    """
    try:
        sig = inspect.signature(brain_cls.__init__)
        accepted = set(sig.parameters.keys())  # inclui self
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        return brain_cls(conn, **filtered)
    except TypeError:
        # fallback: tenta só com conn
        return brain_cls(conn)


# ==========================
# TREINO (N -> N+1)
# ==========================
def treinar_pendencias(conn, limite_concursos: Optional[int] = None) -> Dict[str, Any]:
    concursos = _fetch_all_concursos(conn)
    if len(concursos) < 2:
        raise RuntimeError("❌ Banco tem poucos concursos. Rode START/startBD.py e/ou START/update_concursos.py.")

    ck = _get_checkpoint(conn)
    max_treino = concursos[-2]
    pendentes = [c for c in concursos if c > ck and c <= max_treino]

    if limite_concursos is not None:
        pendentes = pendentes[: int(limite_concursos)]

    if not pendentes:
        return {"status": "ok", "message": "Sem novos concursos para treinar.", "checkpoint": ck}

    _log("=========================================")
    _log("🧠 TRAINER_V2 — TREINAMENTO INCREMENTAL")
    _log("=========================================")
    _log(f"📌 Checkpoint atual : {ck}")
    _log(f"📌 Treinando de     : {pendentes[0]} até {pendentes[-1]}")
    _log(f"📌 Total pendente   : {len(pendentes)}")
    _log("=========================================")

    # BrainHub + brains
    hub = BrainHub(conn)

    # IMPORTANTÍSSIMO: usamos instanciação adaptativa (não quebra por kwargs)
    hub.register(_instantiate_brain(StatFreqGlobalBrain, conn))
    hub.register(_instantiate_brain(StatFreqRecenteBrain, conn, janela=120))
    hub.register(_instantiate_brain(TemporalAtrasoBrain, conn))

    # ✅ aqui resolve o seu problema: se o cérebro não aceitar janela, ele ignora
    hub.register(_instantiate_brain(StatNucleoSatelitesBrain, conn, janela=300))

    hub.register(_instantiate_brain(ExplorTotalDezenasAutoBrain, conn))
    hub.register(_instantiate_brain(StatEliteMemoryBrain, conn))
    hub.register(_instantiate_brain(StatParidadeFaixasBrain, conn))
    hub.register(_instantiate_brain(StructuralPatternShapeBrain, conn))
    hub.register(_instantiate_brain(StructuralCoreProtectBrain, conn))
    for brain in build_heuristic_brains(conn):
        hub.register(brain)

    hub.load_all()  # carrega estado persistido dos cérebros

    total_mem = 0
    total_14 = 0
    total_15 = 0

    pbar = tqdm(pendentes, desc="Treinando concursos", unit="concurso")
    t0_global = time.time()
    last_commit_ts = time.time()

    for idx, concurso_n in enumerate(pbar, 1):
        resultado_n1 = _fetch_result(conn, concurso_n + 1)
        if not resultado_n1:
            continue

        context_base = _build_context(conn, concurso_n=concurso_n, janela_recente=JANELA_RECENTE)

        tentativa = 1
        t0 = time.time()

        # --------------------------
        # 15 dezenas
        # --------------------------
        cand15 = hub.generate_games(
            context=context_base,
            size=15,
            per_brain=CANDIDATOS_POR_CEREBRO,
            top_n=TOP_N_POR_TAMANHO,
        )
        top15 = _rank_and_select(cand15, resultado_n1, AVALIAR_TOP_K, tipo=15)

        # --------------------------
        # 18 dezenas
        # --------------------------
        cand18 = hub.generate_games(
            context=context_base,
            size=18,
            per_brain=CANDIDATOS_POR_CEREBRO,
            top_n=TOP_N_POR_TAMANHO,
        )
        top18 = _rank_and_select(cand18, resultado_n1, AVALIAR_TOP_K, tipo=18)

        tempo_exec = time.time() - t0

        # --------------------------
        # Persistência + aprendizado
        # --------------------------
        for item in (top15 + top18):
            jogo = item["jogo"]
            acertos = item["acertos"]
            score = item["score"]
            brain_id = item["brain_id"]
            tipo = item["tipo"]

            _insert_tentativa(
                conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                tentativa=tentativa,
                dezenas=jogo,
                acertos=acertos,
                score=score,
                brain_id=brain_id,
                tempo_exec=tempo_exec,
            )

            if acertos >= SALVAR_MEMORIA_MIN:
                ok = _insert_memoria_forte(
                    conn,
                    concurso_n=concurso_n,
                    concurso_n1=concurso_n + 1,
                    tipo_jogo=tipo,
                    dezenas=jogo,
                    acertos=acertos,
                    peso=1.0,
                    origem=f"{SCORE_TAG}:{brain_id}",
                )
                if ok:
                    total_mem += 1

            if acertos >= 14:
                total_14 += 1
            if acertos == 15:
                total_15 += 1

            hub.learn(
                concurso_n=concurso_n,
                jogo=jogo,
                resultado_n1=resultado_n1,
                pontos=acertos,
                context=context_base,
                brain_id=brain_id,
            )

            tentativa += 1

        _set_checkpoint(conn, concurso_n, etapa="trainer_v2")

        if idx % int(PERSISTIR_A_CADA) == 0:
            hub.save_all()

        # ✅ tenta commit a cada 30 min (só no GitHub Actions)
        last_commit_ts = _try_commit_if_good_every(last_commit_ts, interval_min=29)

        melhor15 = top15[0]["acertos"] if top15 else 0
        melhor18 = top18[0]["acertos"] if top18 else 0
        pbar.set_postfix({"melhor15": melhor15, "melhor18": melhor18, "mem+": total_mem, "14+": total_14, "15": total_15})

    hub.save_all()

    dur = time.time() - t0_global
    resumo = {
        "status": "ok",
        "checkpoint_final": _get_checkpoint(conn),
        "duracao_seg": round(dur, 2),
        "memorias_salvas": total_mem,
        "total_14+": total_14,
        "total_15": total_15,
        "timestamp": now_str(),
    }

    _log("=========================================")
    _log("✅ TRAINER_V2 — TREINO FINALIZADO")
    _log("=========================================")
    _log(f"⏱️ Duração total    : {resumo['duracao_seg']}s")
    _log(f"📌 Checkpoint final : {resumo['checkpoint_final']}")
    _log(f"💾 Memórias (>=11)  : {resumo['memorias_salvas']}")
    _log(f"🔥 Acertos 14+      : {resumo['total_14+']}")
    _log(f"🏆 Acertos 15       : {resumo['total_15']}")
    _log("=========================================")

    return resumo


def run(loop: bool, sleep_min: int, limite_concursos: Optional[int]) -> None:
    """
    Modo 24/7:
    - roda treinos pendentes
    - se não tiver novos concursos, dorme e repete
    """
    while True:
        conn = get_conn()
        try:
            resumo = treinar_pendencias(conn, limite_concursos=limite_concursos)
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not loop:
            break

        if resumo.get("message") == "Sem novos concursos para treinar.":
            _log(f"🕒 Sem novos concursos. Dormindo {sleep_min} min...")
            time.sleep(max(1, int(sleep_min)) * 60)
        else:
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="TRAINER_V2 — Treinamento incremental N->N+1 (BrainHub)")
    parser.add_argument("--loop", action="store_true", help="Roda em loop (24/7), dormindo quando não houver novos concursos.")
    parser.add_argument("--sleep-min", type=int, default=30, help="Minutos para dormir quando não houver novos concursos (modo --loop).")
    parser.add_argument("--limite", type=int, default=None, help="Limitar quantos concursos treinar nesta execução (debug).")
    args = parser.parse_args()

    run(loop=bool(args.loop), sleep_min=int(args.sleep_min), limite_concursos=args.limite)


if __name__ == "__main__":
    main()
