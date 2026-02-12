# training/trainer_v2.py
from __future__ import annotations

import os
import sys
import subprocess
import json
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
from training.brains.structural.anti_absence_brain import StructuralAntiAbsenceBrain
from training.brains.brain_step_sequences import HeuristicStepSequencesBrain


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
HIGH_HIT_FOCUS_15 = 0.06             # bônus extra para cérebros com histórico 14/15 (apenas size=15)

# Auto-gestão de cérebros com base em performance histórica
AUTO_DISABLE_MIN_GAMES = 3000        # só considera desabilitar após volume mínimo
AUTO_DISABLE_KEEP_TOP_Q15 = 20       # mantém os top cérebros por q15 sempre habilitados
AUTO_DISABLE_KEEP_TOP_Q14 = 20       # mantém os top cérebros por q14 sempre habilitados
AUTO_DISABLE_RECENT_WINDOW = 240      # janela recente para score temporal na auto-gestão
AUTO_DISABLE_RECENT_WEIGHT = 0.70     # peso do recente no score temporal


# ==========================
# UTIL
# ==========================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{now_str()}] {msg}")


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
        "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10", "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18",
        "acertos", "score", "score_tag", "brain_id", "tempo_exec", "timestamp",
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
        "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10", "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18",
        "acertos", "peso", "origem", "timestamp",
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
    ultimo = historico[-1] if historico else (_fetch_result(conn, concurso_n) or [])

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


def _compute_brain_enable_decisions(
    perf_rows: List[Dict[str, Any]],
    min_games: int,
    keep_top_q15: int,
    keep_top_q14: int,
    recent_weight: float = AUTO_DISABLE_RECENT_WEIGHT,
) -> Dict[str, bool]:
    """
    Calcula decisão ON/OFF por cérebro a partir de performance agregada.

    Regra principal:
    - Desabilita temporariamente cérebros com q15=0 e jogos>=min_games.
    - Protege os top cérebros por q15 e q14 para evitar apagar diversidade útil.
    """
    if not perf_rows:
        return {}

    recent_weight = max(0.0, min(1.0, float(recent_weight)))

    def _blend_score(r: Dict[str, Any]) -> float:
        q15_g = int(r.get("q15", 0))
        q14_g = int(r.get("q14", 0))
        m_g = float(r.get("media", 0.0))
        q15_r = int(r.get("q15_recent", q15_g))
        q14_r = int(r.get("q14_recent", q14_g))
        m_r = float(r.get("media_recent", m_g))

        global_score = (q15_g * 8.0) + (q14_g * 2.0) + (m_g * 0.2)
        recent_score = (q15_r * 8.0) + (q14_r * 2.0) + (m_r * 0.2)
        return (recent_weight * recent_score) + ((1.0 - recent_weight) * global_score)

    top_q15 = {
        str(r["brain_id"])
        for r in sorted(perf_rows, key=lambda x: (int(x["q15"]), _blend_score(x)), reverse=True)[: max(0, int(keep_top_q15))]
    }
    top_q14 = {
        str(r["brain_id"])
        for r in sorted(perf_rows, key=lambda x: (int(x["q14"]), _blend_score(x)), reverse=True)[: max(0, int(keep_top_q14))]
    }
    protected = top_q15 | top_q14

    decisions: Dict[str, bool] = {}
    for r in perf_rows:
        bid = str(r["brain_id"])
        jogos = int(r["jogos"])
        q15 = int(r["q15"])
        if bid in protected:
            decisions[bid] = True
            continue

        disable = (jogos >= int(min_games)) and (q15 <= 0)
        decisions[bid] = not disable

    return decisions


def _auto_manage_brains_enabled(
    conn,
    enabled: bool,
    min_games: int,
    keep_top_q15: int,
    keep_top_q14: int,
    recent_window: int,
    recent_weight: float,
) -> Dict[str, int]:
    """
    Liga/desliga temporariamente cérebros conforme performance histórica.
    Isso atualiza apenas a flag `habilitado` na tabela `cerebros`.
    """
    if not enabled:
        return {"updated_on": 0, "updated_off": 0, "total": 0}

    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.brain_id,
               COALESCE(SUM(p.jogos_gerados), 0) AS jogos,
               COALESCE(AVG(p.media_pontos), 0) AS media,
               COALESCE(SUM(p.qtd_14), 0) AS q14,
               COALESCE(SUM(p.qtd_15), 0) AS q15
        FROM cerebros c
        LEFT JOIN cerebro_performance p ON p.cerebro_id = c.id
        GROUP BY c.brain_id
        """
    )
    rows_raw = cur.fetchall()
    perf_rows = [
        {
            "brain_id": r[0],
            "jogos": int(r[1] or 0),
            "media": float(r[2] or 0.0),
            "q14": int(r[3] or 0),
            "q15": int(r[4] or 0),
            "q14_recent": 0,
            "q15_recent": 0,
            "media_recent": 0.0,
        }
        for r in rows_raw
    ]

    # agrega janela recente para score temporal
    recent_window = max(1, int(recent_window))
    cur.execute("SELECT MAX(concurso) FROM cerebro_performance")
    mx = cur.fetchone()
    max_concurso = int(mx[0]) if mx and mx[0] is not None else 0
    if max_concurso > 0:
        min_recent = max(1, max_concurso - recent_window + 1)
        cur.execute(
            """
            SELECT c.brain_id,
                   COALESCE(AVG(p.media_pontos), 0) AS media_recent,
                   COALESCE(SUM(p.qtd_14), 0) AS q14_recent,
                   COALESCE(SUM(p.qtd_15), 0) AS q15_recent
            FROM cerebro_performance p
            JOIN cerebros c ON c.id = p.cerebro_id
            WHERE p.concurso >= ?
            GROUP BY c.brain_id
            """,
            (int(min_recent),),
        )
        recent_map = {
            str(bid): {
                "media_recent": float(mr or 0.0),
                "q14_recent": int(q14r or 0),
                "q15_recent": int(q15r or 0),
            }
            for bid, mr, q14r, q15r in cur.fetchall()
        }
        for row in perf_rows:
            row.update(recent_map.get(str(row["brain_id"]), {}))

    decisions = _compute_brain_enable_decisions(
        perf_rows,
        min_games=min_games,
        keep_top_q15=keep_top_q15,
        keep_top_q14=keep_top_q14,
        recent_weight=recent_weight,
    )
    if not decisions:
        return {"updated_on": 0, "updated_off": 0, "total": 0}

    updated_on = 0
    updated_off = 0
    for bid, should_enable in decisions.items():
        cur.execute("SELECT habilitado FROM cerebros WHERE brain_id=?", (bid,))
        row = cur.fetchone()
        if not row:
            continue
        current = int(row[0] or 0)
        target = 1 if should_enable else 0
        if current == target:
            continue

        cur.execute(
            "UPDATE cerebros SET habilitado=?, atualizado_em=? WHERE brain_id=?",
            (target, now_str(), bid),
        )
        if target == 1:
            updated_on += 1
        else:
            updated_off += 1

    conn.commit()
    return {"updated_on": updated_on, "updated_off": updated_off, "total": len(decisions)}


def _build_dynamic_per_brain_map(
    conn,
    base_per_brain: int,
    size: int,
    recent_window: int = 180,
) -> Dict[str, int]:
    """
    Alocação dinâmica de candidatos por cérebro com base em fase recente.
    Mantém o orçamento total próximo do valor base por cérebro.
    """
    cur = conn.cursor()
    cur.execute("SELECT MAX(concurso) FROM cerebro_performance")
    row = cur.fetchone()
    max_concurso = int(row[0]) if row and row[0] is not None else 0
    if max_concurso <= 0:
        return {}

    min_recent = max(1, max_concurso - max(1, int(recent_window)) + 1)
    cur.execute(
        """
        SELECT c.brain_id,
               COALESCE(SUM(p.qtd_14), 0) AS q14,
               COALESCE(SUM(p.qtd_15), 0) AS q15,
               COALESCE(AVG(p.media_pontos), 0) AS media
        FROM cerebro_performance p
        JOIN cerebros c ON c.id = p.cerebro_id
        WHERE p.concurso >= ?
        GROUP BY c.brain_id
        """,
        (int(min_recent),),
    )
    rows = cur.fetchall()
    if not rows:
        return {}

    scored = []
    for bid, q14, q15, media in rows:
        # 15 pontos pesa mais para size=15
        w15 = 10.0 if int(size) == 15 else 6.0
        sc = (w15 * float(q15 or 0)) + (2.0 * float(q14 or 0)) + (0.3 * float(media or 0.0))
        scored.append((str(bid), max(0.0, sc)))

    total_sc = sum(s for _, s in scored)
    if total_sc <= 0:
        return {}

    n_brains = len(scored)
    total_budget = int(base_per_brain) * n_brains
    min_pb = max(10, int(base_per_brain * 0.35))
    max_pb = max(min_pb, int(base_per_brain * 1.75))

    alloc: Dict[str, int] = {}
    for bid, sc in scored:
        raw = int(round((sc / total_sc) * total_budget))
        alloc[bid] = max(min_pb, min(max_pb, raw))

    return alloc


def _ensure_experiment_tables(conn) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS experimentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            tipo TEXT,
            commit_sha TEXT,
            config_json TEXT,
            status TEXT DEFAULT 'running',
            inicio_concurso INTEGER,
            fim_concurso INTEGER,
            iniciado_em TEXT,
            finalizado_em TEXT,
            observacao TEXT
        );
        CREATE TABLE IF NOT EXISTS experimentos_resultados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experimento_id INTEGER NOT NULL,
            brain_id TEXT NOT NULL,
            jogos INTEGER DEFAULT 0,
            media REAL DEFAULT 0,
            q14 INTEGER DEFAULT 0,
            q15 INTEGER DEFAULT 0,
            q14_rate REAL DEFAULT 0,
            q15_rate REAL DEFAULT 0,
            criado_em TEXT
        );
        """
    )
    conn.commit()


def _ensure_runtime_governance_tables(conn) -> None:
    """
    Garante criação dinâmica (IF NOT EXISTS) das tabelas de governança
    e suporte de performance, sem remover/alterar dados existentes.
    """
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS cerebros (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brain_id TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL DEFAULT '',
            categoria TEXT NOT NULL DEFAULT '',
            versao TEXT NOT NULL DEFAULT 'v1',
            habilitado INTEGER DEFAULT 1,
            criado_em TEXT,
            atualizado_em TEXT
        );

        CREATE TABLE IF NOT EXISTS cerebro_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cerebro_id INTEGER NOT NULL,
            concurso INTEGER NOT NULL,
            jogos_gerados INTEGER DEFAULT 0,
            media_pontos REAL DEFAULT 0,
            qtd_11 INTEGER DEFAULT 0,
            qtd_12 INTEGER DEFAULT 0,
            qtd_13 INTEGER DEFAULT 0,
            qtd_14 INTEGER DEFAULT 0,
            qtd_15 INTEGER DEFAULT 0,
            atualizado_em TEXT,
            UNIQUE(cerebro_id, concurso)
        );
        """
    )
    conn.commit()
    _ensure_experiment_tables(conn)


def _start_experiment(conn, name: str, inicio_concurso: int, config: Dict[str, Any]) -> int:
    _ensure_experiment_tables(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO experimentos (nome, tipo, commit_sha, config_json, status, inicio_concurso, iniciado_em)
        VALUES (?, 'trainer_v2', ?, ?, 'running', ?, ?)
        """,
        (
            str(name),
            os.environ.get("GITHUB_SHA", ""),
            json.dumps(config, ensure_ascii=False),
            int(inicio_concurso),
            now_str(),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def _finish_experiment(conn, exp_id: int, fim_concurso: int) -> None:
    _ensure_experiment_tables(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT c.brain_id,
               COALESCE(SUM(p.jogos_gerados),0) AS jogos,
               COALESCE(AVG(p.media_pontos),0) AS media,
               COALESCE(SUM(p.qtd_14),0) AS q14,
               COALESCE(SUM(p.qtd_15),0) AS q15
        FROM cerebro_performance p
        JOIN cerebros c ON c.id = p.cerebro_id
        WHERE p.concurso <= ?
        GROUP BY c.brain_id
        """,
        (int(fim_concurso),),
    )
    rows = cur.fetchall()

    for bid, jogos, media, q14, q15 in rows:
        jogos_i = int(jogos or 0)
        q14_i = int(q14 or 0)
        q15_i = int(q15 or 0)
        q14_rate = (q14_i / jogos_i) if jogos_i > 0 else 0.0
        q15_rate = (q15_i / jogos_i) if jogos_i > 0 else 0.0
        cur.execute(
            """
            INSERT INTO experimentos_resultados
            (experimento_id, brain_id, jogos, media, q14, q15, q14_rate, q15_rate, criado_em)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                int(exp_id),
                str(bid),
                jogos_i,
                float(media or 0.0),
                q14_i,
                q15_i,
                float(q14_rate),
                float(q15_rate),
                now_str(),
            ),
        )

    cur.execute(
        "UPDATE experimentos SET status='done', fim_concurso=?, finalizado_em=? WHERE id=?",
        (int(fim_concurso), now_str(), int(exp_id)),
    )
    conn.commit()


# ==========================
# TREINO (N -> N+1)
# ==========================
def treinar_pendencias(
    conn,
    limite_concursos: Optional[int] = None,
    exploration_rate: Optional[float] = None,
    max_brain_share: Optional[float] = None,
    high_hit_focus: Optional[float] = None,
    quota_enabled: Optional[bool] = None,
    quota_max_per_brain: Optional[int] = None,
    consensus_enabled: Optional[bool] = None,
    consensus_bonus: Optional[float] = None,
    consensus_min_votes: Optional[int] = None,
    steps_mutation_rate: float = 0.10,
    steps_exploration_rate: float = 0.10,
    steps_delta_max: int = 3,
    steps_wrap_mode: str = "wrap",
    steps_max_attempts_per_game: int = 50,
    auto_manage_brains: bool = True,
    auto_disable_min_games: int = AUTO_DISABLE_MIN_GAMES,
    auto_disable_keep_top_q15: int = AUTO_DISABLE_KEEP_TOP_Q15,
    auto_disable_keep_top_q14: int = AUTO_DISABLE_KEEP_TOP_Q14,
    auto_disable_recent_window: int = AUTO_DISABLE_RECENT_WINDOW,
    auto_disable_recent_weight: float = AUTO_DISABLE_RECENT_WEIGHT,
    dynamic_per_brain: bool = False,
    dynamic_per_brain_recent_window: int = 180,
    strong_consensus_enabled: bool = False,
    strong_consensus_bonus: float = 0.0,
    collapse_penalty_enabled: bool = False,
    collapse_penalty: float = 0.0,
    collapse_votes_threshold: int = 5,
    experiment_name: Optional[str] = None,
) -> Dict[str, Any]:
    _ensure_runtime_governance_tables(conn)

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

    manage = _auto_manage_brains_enabled(
        conn,
        enabled=bool(auto_manage_brains),
        min_games=int(auto_disable_min_games),
        keep_top_q15=int(auto_disable_keep_top_q15),
        keep_top_q14=int(auto_disable_keep_top_q14),
        recent_window=int(auto_disable_recent_window),
        recent_weight=float(auto_disable_recent_weight),
    )

    exp_id: Optional[int] = None
    if experiment_name:
        exp_id = _start_experiment(
            conn,
            name=str(experiment_name),
            inicio_concurso=int(pendentes[0]),
            config={
                "limite_concursos": limite_concursos,
                "exploration_rate": exploration_rate,
                "max_brain_share": max_brain_share,
                "auto_manage_brains": auto_manage_brains,
                "dynamic_per_brain": dynamic_per_brain,
                "strong_consensus_enabled": strong_consensus_enabled,
                "collapse_penalty_enabled": collapse_penalty_enabled,
            },
        )

    _log("=========================================")
    _log("🧠 TRAINER_V2 — TREINAMENTO INCREMENTAL")
    _log("=========================================")
    _log(f"📌 Checkpoint atual : {ck}")
    _log(f"📌 Treinando de     : {pendentes[0]} até {pendentes[-1]}")
    _log(f"📌 Total pendente   : {len(pendentes)}")
    if bool(auto_manage_brains):
        _log(
            "🧩 Auto-gestão cérebros: "
            f"ON={manage.get('updated_on', 0)} OFF={manage.get('updated_off', 0)} "
            f"(avaliados={manage.get('total', 0)})"
        )
    _log("=========================================")

    # BrainHub + brains
    hub_kwargs: Dict[str, Any] = {}
    if exploration_rate is not None:
        hub_kwargs["exploration_rate"] = float(exploration_rate)
    if max_brain_share is not None:
        hub_kwargs["max_brain_share"] = float(max_brain_share)
    if high_hit_focus is None:
        high_hit_focus = float(HIGH_HIT_FOCUS_15)
    hub_kwargs["high_hit_focus"] = float(high_hit_focus)
    if quota_enabled is not None:
        hub_kwargs["quota_enabled"] = bool(quota_enabled)
    if quota_max_per_brain is not None:
        hub_kwargs["quota_max_per_brain"] = int(quota_max_per_brain)
    if consensus_enabled is not None:
        hub_kwargs["consensus_enabled"] = bool(consensus_enabled)
    if consensus_bonus is not None:
        hub_kwargs["consensus_bonus"] = float(consensus_bonus)
    if consensus_min_votes is not None:
        hub_kwargs["consensus_min_votes"] = int(consensus_min_votes)
    hub_kwargs["strong_consensus_enabled"] = bool(strong_consensus_enabled)
    hub_kwargs["strong_consensus_bonus"] = float(strong_consensus_bonus)
    hub_kwargs["collapse_penalty_enabled"] = bool(collapse_penalty_enabled)
    hub_kwargs["collapse_penalty"] = float(collapse_penalty)
    hub_kwargs["collapse_votes_threshold"] = int(collapse_votes_threshold)

    hub = BrainHub(conn, **hub_kwargs)

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
    hub.register(_instantiate_brain(StructuralAntiAbsenceBrain, conn))
    hub.register(
        _instantiate_brain(
            HeuristicStepSequencesBrain,
            conn,
            mutation_rate=steps_mutation_rate,
            exploration_rate=steps_exploration_rate,
            delta_max=steps_delta_max,
            wrap_mode=steps_wrap_mode,
            max_attempts_per_game=steps_max_attempts_per_game,
        )
    )

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
        per_brain_15: Any = int(CANDIDATOS_POR_CEREBRO)
        per_brain_18: Any = int(CANDIDATOS_POR_CEREBRO)
        if bool(dynamic_per_brain):
            alloc_map = _build_dynamic_per_brain_map(
                conn,
                base_per_brain=int(CANDIDATOS_POR_CEREBRO),
                size=15,
                recent_window=int(dynamic_per_brain_recent_window),
            )
            if alloc_map:
                per_brain_15 = alloc_map
                per_brain_18 = alloc_map

        cand15 = hub.generate_games(
            context=context_base,
            size=15,
            per_brain=per_brain_15,
            top_n=TOP_N_POR_TAMANHO,
        )
        top15 = _rank_and_select(cand15, resultado_n1, AVALIAR_TOP_K, tipo=15)

        # --------------------------
        # 18 dezenas
        # --------------------------
        cand18 = hub.generate_games(
            context=context_base,
            size=18,
            per_brain=per_brain_18,
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

        # ✅ tenta commit a cada ~29 min (só no GitHub Actions)
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

    if exp_id is not None:
        _finish_experiment(conn, exp_id=exp_id, fim_concurso=int(resumo["checkpoint_final"]))

    return resumo


def run(
    loop: bool,
    sleep_min: int,
    limite_concursos: Optional[int],
    exploration_rate: Optional[float],
    max_brain_share: Optional[float],
    high_hit_focus: Optional[float],
    quota_enabled: Optional[bool],
    quota_max_per_brain: Optional[int],
    consensus_enabled: Optional[bool],
    consensus_bonus: Optional[float],
    consensus_min_votes: Optional[int],
    steps_mutation_rate: float,
    steps_exploration_rate: float,
    steps_delta_max: int,
    steps_wrap_mode: str,
    steps_max_attempts_per_game: int,
    auto_manage_brains: bool,
    auto_disable_min_games: int,
    auto_disable_keep_top_q15: int,
    auto_disable_keep_top_q14: int,
    auto_disable_recent_window: int,
    auto_disable_recent_weight: float,
    dynamic_per_brain: bool,
    dynamic_per_brain_recent_window: int,
    strong_consensus_enabled: bool,
    strong_consensus_bonus: float,
    collapse_penalty_enabled: bool,
    collapse_penalty: float,
    collapse_votes_threshold: int,
    experiment_name: Optional[str],
) -> None:
    """
    Modo 24/7:
    - roda treinos pendentes
    - se não tiver novos concursos, dorme e repete
    """
    while True:
        conn = get_conn()
        try:
            resumo = treinar_pendencias(
                conn,
                limite_concursos=limite_concursos,
                exploration_rate=exploration_rate,
                max_brain_share=max_brain_share,
                high_hit_focus=high_hit_focus,
                quota_enabled=quota_enabled,
                quota_max_per_brain=quota_max_per_brain,
                consensus_enabled=consensus_enabled,
                consensus_bonus=consensus_bonus,
                consensus_min_votes=consensus_min_votes,
                steps_mutation_rate=steps_mutation_rate,
                steps_exploration_rate=steps_exploration_rate,
                steps_delta_max=steps_delta_max,
                steps_wrap_mode=steps_wrap_mode,
                steps_max_attempts_per_game=steps_max_attempts_per_game,
                auto_manage_brains=auto_manage_brains,
                auto_disable_min_games=auto_disable_min_games,
                auto_disable_keep_top_q15=auto_disable_keep_top_q15,
                auto_disable_keep_top_q14=auto_disable_keep_top_q14,
                auto_disable_recent_window=auto_disable_recent_window,
                auto_disable_recent_weight=auto_disable_recent_weight,
                dynamic_per_brain=dynamic_per_brain,
                dynamic_per_brain_recent_window=dynamic_per_brain_recent_window,
                strong_consensus_enabled=strong_consensus_enabled,
                strong_consensus_bonus=strong_consensus_bonus,
                collapse_penalty_enabled=collapse_penalty_enabled,
                collapse_penalty=collapse_penalty,
                collapse_votes_threshold=collapse_votes_threshold,
                experiment_name=experiment_name,
            )
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


def main() -> None:
    parser = argparse.ArgumentParser(description="TRAINER_V2 — Treinamento incremental N->N+1 (BrainHub)")
    parser.add_argument("--loop", action="store_true", help="Roda em loop (24/7), dormindo quando não houver novos concursos.")
    parser.add_argument("--sleep-min", type=int, default=30, help="Minutos para dormir quando não houver novos concursos (modo --loop).")
    parser.add_argument("--limite", type=int, default=None, help="Limitar quantos concursos treinar nesta execução (debug).")

    parser.add_argument("--exploration-rate", type=float, default=None, help="Exploração do BrainHub (opcional).")
    parser.add_argument("--max-brain-share", type=float, default=None, help="Limite por cérebro no BrainHub (opcional).")
    parser.add_argument(
        "--high-hit-focus",
        type=float,
        default=None,
        help="Bônus extra para cérebros com histórico 14/15 (apenas size=15).",
    )

    parser.add_argument("--quota-enabled", action="store_true", help="Ativar quota por cérebro no Top N.")
    parser.add_argument("--quota-max-per-brain", type=int, default=0, help="Limite absoluto por cérebro no Top N.")

    parser.add_argument("--consensus-enabled", action="store_true", help="Ativar bônus por consenso entre cérebros.")
    parser.add_argument("--consensus-bonus", type=float, default=0.02, help="Bônus por consenso de candidatos.")
    parser.add_argument("--consensus-min-votes", type=int, default=2, help="Mínimo de votos para bônus de consenso.")

    parser.add_argument("--steps-mutation-rate", type=float, default=0.10, help="Mutation rate do brain step sequences.")
    parser.add_argument("--steps-exploration-rate", type=float, default=0.10, help="Exploration rate do brain step sequences.")
    parser.add_argument("--steps-delta-max", type=int, default=3, help="Delta máximo (passo) para step sequences.")
    parser.add_argument("--steps-wrap-mode", type=str, default="wrap", help="Modo de wrap (ex: wrap) para step sequences.")
    parser.add_argument(
        "--steps-max-attempts-per-game",
        type=int,
        default=50,
        help="Tentativas por jogo no brain de step sequences.",
    )
    parser.add_argument(
        "--disable-auto-manage-brains",
        action="store_true",
        help="Desativa auto-gestão de habilitado dos cérebros por performance.",
    )
    parser.add_argument(
        "--auto-disable-min-games",
        type=int,
        default=AUTO_DISABLE_MIN_GAMES,
        help="Mínimo de jogos para desabilitar cérebro com q15=0.",
    )
    parser.add_argument(
        "--auto-disable-keep-top-q15",
        type=int,
        default=AUTO_DISABLE_KEEP_TOP_Q15,
        help="Protege top cérebros por q15 de desativação.",
    )
    parser.add_argument(
        "--auto-disable-keep-top-q14",
        type=int,
        default=AUTO_DISABLE_KEEP_TOP_Q14,
        help="Protege top cérebros por q14 de desativação.",
    )
    parser.add_argument(
        "--auto-disable-recent-window",
        type=int,
        default=AUTO_DISABLE_RECENT_WINDOW,
        help="Janela recente (concursos) usada na auto-gestão temporal de cérebros.",
    )
    parser.add_argument(
        "--auto-disable-recent-weight",
        type=float,
        default=AUTO_DISABLE_RECENT_WEIGHT,
        help="Peso da performance recente na auto-gestão temporal (0..1).",
    )
    parser.add_argument("--dynamic-per-brain", action="store_true", help="Ativa alocação dinâmica de candidatos por cérebro.")
    parser.add_argument(
        "--dynamic-per-brain-recent-window",
        type=int,
        default=180,
        help="Janela recente para calcular alocação dinâmica por cérebro.",
    )
    parser.add_argument("--strong-consensus-enabled", action="store_true", help="Ativa consenso forte ponderado no BrainHub.")
    parser.add_argument("--strong-consensus-bonus", type=float, default=0.0, help="Bônus por voto ponderado no consenso forte.")
    parser.add_argument("--collapse-penalty-enabled", action="store_true", help="Ativa penalidade de colapso por excesso de votos no mesmo jogo.")
    parser.add_argument("--collapse-penalty", type=float, default=0.0, help="Valor da penalidade de colapso.")
    parser.add_argument("--collapse-votes-threshold", type=int, default=5, help="Qtd de votos para disparar penalidade de colapso.")
    parser.add_argument("--experiment-name", type=str, default=None, help="Nome do experimento para versionar resultados (A/B).")

    args = parser.parse_args()

    run(
        loop=bool(args.loop),
        sleep_min=int(args.sleep_min),
        limite_concursos=args.limite,
        exploration_rate=args.exploration_rate,
        max_brain_share=args.max_brain_share,
        high_hit_focus=args.high_hit_focus,
        quota_enabled=bool(args.quota_enabled),
        quota_max_per_brain=max(0, int(args.quota_max_per_brain)),
        consensus_enabled=bool(args.consensus_enabled),
        consensus_bonus=float(args.consensus_bonus),
        consensus_min_votes=max(2, int(args.consensus_min_votes)),
        steps_mutation_rate=float(args.steps_mutation_rate),
        steps_exploration_rate=float(args.steps_exploration_rate),
        steps_delta_max=int(args.steps_delta_max),
        steps_wrap_mode=str(args.steps_wrap_mode),
        steps_max_attempts_per_game=int(args.steps_max_attempts_per_game),
        auto_manage_brains=not bool(args.disable_auto_manage_brains),
        auto_disable_min_games=max(0, int(args.auto_disable_min_games)),
        auto_disable_keep_top_q15=max(0, int(args.auto_disable_keep_top_q15)),
        auto_disable_keep_top_q14=max(0, int(args.auto_disable_keep_top_q14)),
        auto_disable_recent_window=max(1, int(args.auto_disable_recent_window)),
        auto_disable_recent_weight=max(0.0, min(1.0, float(args.auto_disable_recent_weight))),
        dynamic_per_brain=bool(args.dynamic_per_brain),
        dynamic_per_brain_recent_window=max(1, int(args.dynamic_per_brain_recent_window)),
        strong_consensus_enabled=bool(args.strong_consensus_enabled),
        strong_consensus_bonus=max(0.0, float(args.strong_consensus_bonus)),
        collapse_penalty_enabled=bool(args.collapse_penalty_enabled),
        collapse_penalty=max(0.0, float(args.collapse_penalty)),
        collapse_votes_threshold=max(2, int(args.collapse_votes_threshold)),
        experiment_name=(str(args.experiment_name).strip() if args.experiment_name else None),
    )


if __name__ == "__main__":
    main()
