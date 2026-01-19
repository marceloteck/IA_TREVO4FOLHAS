# training/trainer_v2.py

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Tuple, Optional

from tqdm import tqdm

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub

# Cluster (primeiro cluster pronto)
from training.brains.statistical.freq_global_brain import StatFreqGlobalBrain
from training.brains.statistical.freq_recente_brain import StatFreqRecenteBrain
from training.brains.statistical.pares_brain import StatParesBrain
from training.brains.temporal.atraso_brain import TemporalAtrasoBrain


# ==========================
# Configuração de Treino
# ==========================
JANELA_RECENTE = 300              # janela de histórico para contexto e quentes/frias
CANDIDATOS_POR_CEREBRO = 80       # por tamanho (15/18)
TOP_N_POR_TAMANHO = 60            # candidatos finais por tamanho após hub (diversidade aplicada)
AVALIAR_TOP_K = 40                # quantos candidatos avaliar por tamanho (controle de custo)
SALVAR_MEMORIA_MIN = 11           # salvar memória forte a partir de 11 acertos
PERSISTIR_A_CADA = 5              # salva estados/ checkpoint a cada X concursos
SCORE_TAG = "hub_v3"              # tag do sistema de score

# Tentativas por concurso/tamanho (para auditoria)
TENTATIVAS_BASE = 1               # contador inicial


# ==========================
# Utilitários
# ==========================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dezenas_to_text(dezenas: List[int]) -> str:
    return ",".join(str(int(x)) for x in sorted(dezenas))


def text_to_dezenas(s: str) -> List[int]:
    parts = [p.strip() for p in str(s).split(",") if p.strip()]
    return [int(p) for p in parts]


def contar_acertos(jogo: List[int], resultado: List[int]) -> int:
    return len(set(jogo) & set(resultado))


# ==========================
# DB helpers
# ==========================
def ensure_core_tables(conn) -> None:
    """
    Garante tabelas mínimas necessárias ao treino.
    (Se você já roda db_schema.sql completo, isso só confirma.)
    """
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS concursos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso INTEGER UNIQUE NOT NULL,
            dezenas TEXT NOT NULL,
            data TEXT
        );

        CREATE TABLE IF NOT EXISTS checkpoint (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ultimo_concurso_processado INTEGER,
            etapa TEXT,
            timestamp TEXT
        );

        CREATE TABLE IF NOT EXISTS tentativas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso_n INTEGER NOT NULL,
            concurso_n1 INTEGER NOT NULL,
            tipo_jogo INTEGER NOT NULL,
            tentativa INTEGER NOT NULL,
            dezenas TEXT NOT NULL,
            acertos INTEGER NOT NULL,
            score REAL NOT NULL,
            score_tag TEXT NOT NULL,
            brain_id TEXT,
            tempo_exec REAL,
            timestamp TEXT
        );

        CREATE TABLE IF NOT EXISTS memoria_jogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso_n INTEGER NOT NULL,
            concurso_n1 INTEGER NOT NULL,
            dezenas TEXT NOT NULL,
            acertos INTEGER NOT NULL,
            peso REAL DEFAULT 1.0,
            origem TEXT,
            timestamp TEXT,
            UNIQUE(concurso_n, concurso_n1, dezenas)
        );

        CREATE TABLE IF NOT EXISTS logs_execucao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            duracao REAL,
            timestamp TEXT
        );
        """
    )
    conn.commit()


def get_checkpoint(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT ultimo_concurso_processado FROM checkpoint WHERE id = 1")
    row = cur.fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


def set_checkpoint(conn, ultimo_concurso: int, etapa: str = "trainer_v2") -> None:
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


def listar_concursos(conn) -> List[int]:
    cur = conn.cursor()
    cur.execute("SELECT concurso FROM concursos ORDER BY concurso ASC")
    return [int(r[0]) for r in cur.fetchall()]


def get_dezenas_concurso(conn, concurso: int) -> Optional[List[int]]:
    cur = conn.cursor()
    cur.execute("SELECT dezenas FROM concursos WHERE concurso = ?", (int(concurso),))
    row = cur.fetchone()
    if not row:
        return None
    return text_to_dezenas(row[0])


def salvar_tentativa(
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
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tentativas (
            concurso_n, concurso_n1, tipo_jogo, tentativa,
            dezenas, acertos, score, score_tag, brain_id, tempo_exec, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(concurso_n),
            int(concurso_n1),
            int(tipo_jogo),
            int(tentativa),
            dezenas_to_text(dezenas),
            int(acertos),
            float(score),
            SCORE_TAG,
            str(brain_id),
            float(tempo_exec),
            now_str(),
        ),
    )
    conn.commit()


def salvar_memoria_forte(
    conn,
    concurso_n: int,
    concurso_n1: int,
    dezenas: List[int],
    acertos: int,
    peso: float = 1.0,
    origem: str = "hub_v3",
) -> None:
    """
    Salva memória >= 11 SEM duplicar: UNIQUE(concurso_n, concurso_n1, dezenas)
    """
    if acertos < SALVAR_MEMORIA_MIN:
        return

    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO memoria_jogos (
            concurso_n, concurso_n1, dezenas, acertos, peso, origem, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(concurso_n),
            int(concurso_n1),
            dezenas_to_text(dezenas),
            int(acertos),
            float(peso),
            str(origem),
            now_str(),
        ),
    )
    conn.commit()


# ==========================
# Seleção final
# ==========================
def rankear_candidatos(
    candidatos: List[Dict[str, Any]],
    resultado_n1: List[int],
    tamanho: int,
    avaliar_top_k: int,
) -> List[Dict[str, Any]]:
    """
    Avalia acertos e gera ranking:
    prioridade 1: acertos
    prioridade 2: score do hub
    """
    # candidatos já vêm em ordem decrescente de score
    avaliados = []
    top = candidatos[:avaliar_top_k]

    for item in top:
        jogo = item["jogo"]
        acertos = contar_acertos(jogo, resultado_n1)
        avaliados.append({
            "jogo": jogo,
            "score": float(item["score"]),
            "brain_id": str(item["brain_id"]),
            "acertos": int(acertos),
            "tipo": int(tamanho),
        })

    avaliados.sort(key=lambda x: (x["acertos"], x["score"]), reverse=True)
    return avaliados


# ==========================
# Trainer principal (N -> N+1)
# ==========================
def treinar_incremental(
    limite_concursos: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Treinamento incremental:
    para cada concurso N, aprende olhando resultado N+1.
    """
    t0_global = time.time()

    conn = get_conn()
    ensure_core_tables(conn)

    concursos = listar_concursos(conn)
    if len(concursos) < 2:
        conn.close()
        raise RuntimeError("❌ Banco tem poucos concursos. Importe concursos antes do treino.")

    # checkpoint: último N já treinado (logo, próximo N = checkpoint+1)
    ck = get_checkpoint(conn)

    # monta BrainHub e registra cérebros
    hub = BrainHub(conn)
    hub.register(StatFreqGlobalBrain(conn))
    hub.register(StatFreqRecenteBrain(conn, janela=120))
    hub.register(StatParesBrain(conn))
    hub.register(TemporalAtrasoBrain(conn))

    # define faixa de treino
    # precisamos garantir que existe N+1, então paramos no penúltimo concurso
    concursos_validos = [c for c in concursos if c > ck]
    if not concursos_validos:
        if verbose:
            print("✅ Nada para treinar. Checkpoint já está no último concurso possível.")
        conn.close()
        return {"status": "ok", "mensagem": "Sem novos concursos para treinar."}

    max_treino = concursos[-2]  # penúltimo
    concursos_validos = [c for c in concursos_validos if c <= max_treino]

    if limite_concursos is not None:
        concursos_validos = concursos_validos[: int(limite_concursos)]

    if verbose:
        print("=========================================")
        print("🧠 TRAINER_V2 — TREINAMENTO INCREMENTAL")
        print("=========================================")
        print(f"📌 Checkpoint atual     : {ck}")
        print(f"📌 Treinando de         : {concursos_validos[0]} até {concursos_validos[-1]}")
        print(f"📌 Total de concursos   : {len(concursos_validos)}")
        print("=========================================\n")

    total_memoria = 0
    total_14 = 0
    total_15 = 0

    progresso = tqdm(concursos_validos, desc="Treinando concursos", unit="concurso")

    for idx, concurso_n in enumerate(progresso, 1):
        # resultado N+1
        resultado_n1 = get_dezenas_concurso(conn, concurso_n + 1)
        if not resultado_n1:
            # sem N+1, não treina
            continue

        # contexto é baseado no concurso N (último conhecido no momento)
        context = hub.build_context(concurso_n, janela_recente=JANELA_RECENTE)

        # ==========================
        # 1) Geração via BrainHub
        # ==========================
        t0 = time.time()
        candidatos_15 = hub.generate_games(
            context=context,
            tamanho=15,
            top_n=TOP_N_POR_TAMANHO,
            candidatos_por_cerebro=CANDIDATOS_POR_CEREBRO,
        )
        candidatos_18 = hub.generate_games(
            context=context,
            tamanho=18,
            top_n=TOP_N_POR_TAMANHO,
            candidatos_por_cerebro=CANDIDATOS_POR_CEREBRO,
        )
        tempo_geracao = time.time() - t0

        # ==========================
        # 2) Avaliação e ranking
        # ==========================
        top15 = rankear_candidatos(candidatos_15, resultado_n1, 15, AVALIAR_TOP_K)
        top18 = rankear_candidatos(candidatos_18, resultado_n1, 18, AVALIAR_TOP_K)

        # ==========================
        # 3) Persistência + aprendizado
        # ==========================
        tentativa = TENTATIVAS_BASE

        # salva tentativas + aprende com o brain autor
        for item in (top15 + top18):
            jogo = item["jogo"]
            acertos = item["acertos"]
            score = item["score"]
            brain_id = item["brain_id"]
            tipo = item["tipo"]

            salvar_tentativa(
                conn=conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                tentativa=tentativa,
                dezenas=jogo,
                acertos=acertos,
                score=score,
                brain_id=brain_id,
                tempo_exec=tempo_geracao,
            )

            # memória forte (>=11)
            if acertos >= SALVAR_MEMORIA_MIN:
                salvar_memoria_forte(
                    conn=conn,
                    concurso_n=concurso_n,
                    concurso_n1=concurso_n + 1,
                    dezenas=jogo,
                    acertos=acertos,
                    peso=1.0,
                    origem=f"{SCORE_TAG}:{brain_id}",
                )
                total_memoria += 1

            # métricas de 14/15
            if acertos >= 14:
                total_14 += 1
            if acertos == 15:
                total_15 += 1

            # aprendizado N -> N+1
            hub.learn_one(
                concurso_n=concurso_n,
                jogo=jogo,
                resultado_n1=resultado_n1,
                pontos=acertos,
                context=context,
                brain_id=brain_id,
            )

            tentativa += 1

        # checkpoint por concurso
        set_checkpoint(conn, concurso_n, etapa="trainer_v2")

        # persiste estado dos cérebros periodicamente
        if idx % PERSISTIR_A_CADA == 0:
            hub.save_all_states()

        # feedback de progresso
        melhor15 = top15[0]["acertos"] if top15 else 0
        melhor18 = top18[0]["acertos"] if top18 else 0

        progresso.set_postfix({
            "melhor15": melhor15,
            "melhor18": melhor18,
            "mem+": total_memoria,
            "14+": total_14,
            "15": total_15,
        })

    # salva tudo no final
    hub.save_all_states()

    dur = time.time() - t0_global

    resumo = {
        "status": "ok",
        "duracao_seg": round(dur, 2),
        "checkpoint_final": get_checkpoint(conn),
        "memorias_salvas": total_memoria,
        "total_14+": total_14,
        "total_15": total_15,
        "timestamp": now_str(),
    }

    conn.close()

    if verbose:
        print("\n=========================================")
        print("✅ TREINAMENTO CONCLUÍDO (TRAINER_V2)")
        print("=========================================")
        print(f"⏱️ Duração total         : {resumo['duracao_seg']}s")
        print(f"📌 Checkpoint final      : {resumo['checkpoint_final']}")
        print(f"💾 Memórias (>=11)       : {resumo['memorias_salvas']}")
        print(f"🔥 Acertos 14+           : {resumo['total_14+']}")
        print(f"🏆 Acertos 15            : {resumo['total_15']}")
        print("=========================================")

    return resumo


# ==========================
# Execução direta
# ==========================
if __name__ == "__main__":
    # limite_concursos=None -> treina tudo que estiver pendente do checkpoint
    treinar_incremental(limite_concursos=None, verbose=True)
