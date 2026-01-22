from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter
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


def jaccard(a: List[int], b: List[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def count_even(jogo: List[int]) -> int:
    return sum(1 for x in jogo if x % 2 == 0)


def max_consecutive_run(jogo: List[int]) -> int:
    s = sorted(jogo)
    if not s:
        return 0
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
    if not safe_table_exists(conn, "memoria_jogos"):
        return []

    cur = conn.cursor()
    cur.execute(
        """
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
# Predições: tabela própria (produção)
# ==========================
def ensure_pred_table(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS predicoes_proximo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            concurso_previsto INTEGER NOT NULL,
            tamanho INTEGER NOT NULL,
            ordem INTEGER NOT NULL,
            d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
            d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
            d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
            d16 INTEGER, d17 INTEGER, d18 INTEGER,
            score_final REAL NOT NULL,
            score_hub REAL,
            score_freq REAL,
            score_mem REAL,
            score_shape REAL,
            perfil TEXT,
            janela INTEGER,
            per_brain INTEGER,
            top_n INTEGER,
            max_sim REAL,
            brains_ativos INTEGER,
            timestamp TEXT,
            UNIQUE(concurso_previsto, tamanho, ordem, d1, d2, d3, d4, d5, d6, d7, d8, d9, d10, d11, d12, d13, d14, d15, d16, d17, d18)
        );
        CREATE INDEX IF NOT EXISTS idx_predicoes_concurso
        ON predicoes_proximo(concurso_previsto);

        CREATE INDEX IF NOT EXISTS idx_predicoes_score
        ON predicoes_proximo(score_final);
        """
    )
    conn.commit()


def insert_pred(
    conn: sqlite3.Connection,
    concurso_previsto: int,
    tamanho: int,
    ordem: int,
    dezenas: List[int],
    score_final: float,
    score_hub: float,
    score_freq: float,
    score_mem: float,
    score_shape: float,
    perfil: str,
    janela: int,
    per_brain: int,
    top_n: int,
    max_sim: float,
    brains_ativos: int,
) -> bool:
    dezenas_sorted = sorted(int(x) for x in dezenas)
    payload = dezenas_sorted + [None] * (18 - len(dezenas_sorted))

    cols = [
        "concurso_previsto", "tamanho", "ordem",
        "d1", "d2", "d3", "d4", "d5", "d6", "d7", "d8", "d9", "d10", "d11", "d12", "d13", "d14", "d15", "d16", "d17", "d18",
        "score_final", "score_hub", "score_freq", "score_mem", "score_shape",
        "perfil", "janela", "per_brain", "top_n", "max_sim", "brains_ativos", "timestamp",
    ]

    values = [
        int(concurso_previsto),
        int(tamanho),
        int(ordem),
        payload[0], payload[1], payload[2], payload[3], payload[4],
        payload[5], payload[6], payload[7], payload[8], payload[9],
        payload[10], payload[11], payload[12], payload[13], payload[14],
        payload[15], payload[16], payload[17],
        float(score_final),
        float(score_hub),
        float(score_freq),
        float(score_mem),
        float(score_shape),
        str(perfil),
        int(janela),
        int(per_brain),
        int(top_n),
        float(max_sim),
        int(brains_ativos),
        now_str(),
    ]

    placeholders = ",".join(["?"] * len(values))
    sql = f"INSERT OR IGNORE INTO predicoes_proximo ({','.join(cols)}) VALUES ({placeholders})"

    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()
    return cur.rowcount > 0


# ==========================
# Registro de cérebros (auto)
# ==========================
def register_brains_auto(conn, hub: BrainHub) -> List[str]:
    loaded: List[str] = []

    def _register(brain) -> None:
        hub.register(brain)
        loaded.append(getattr(brain, "id", brain.__class__.__name__))

    def _try_add(import_path: str, cls_name: str, *args, **kwargs) -> None:
        try:
            mod = __import__(import_path, fromlist=[cls_name])
            cls = getattr(mod, cls_name)
            b = cls(conn, *args, **kwargs)
            _register(b)
        except Exception:
            # silencioso por design (auto-detect)
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
    _try_add("training.brains.structural.core_protect_brain", "StructuralCoreProtectBrain")
    _try_add("training.brains.structural.anti_absence_brain", "StructuralAntiAbsenceBrain")

    try:
        from training.brains.heuristic.heuristic_brains import build_heuristic_brains

        for brain in build_heuristic_brains(conn):
            _register(brain)
    except Exception:
        pass

    return loaded


# ==========================
# Scoring final (explicável)
# ==========================
def score_freq_recente(jogo: List[int], freq: Dict[int, int]) -> float:
    if not jogo:
        return 0.0
    maxf = max(freq.values()) if freq else 1
    if maxf <= 0:
        return 0.0
    return sum(freq.get(int(d), 0) / maxf for d in jogo) / len(jogo)


def score_shape(jogo: List[int], size: int) -> float:
    if not jogo:
        return 0.0

    ev = count_even(jogo)
    run = max_consecutive_run(jogo)

    if size == 15:
        pares_ok = 1.0 if 6 <= ev <= 9 else 0.6
        run_ok = 1.0 if run <= 4 else 0.6
    else:
        pares_ok = 1.0 if 7 <= ev <= 11 else 0.6
        run_ok = 1.0 if run <= 5 else 0.6

    return 0.5 * pares_ok + 0.5 * run_ok


def score_memoria(jogo: List[int], memoria: List[List[int]]) -> float:
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


def get_profile_weights(perfil: str) -> Tuple[float, float, float, float, float]:
    """
    Retorna pesos: (hub, freq, mem, shape, ran)
    """
    perfil = (perfil or "balanceado").lower().strip()
    if perfil == "conservador":
        # mais “forma” + frequência, mais proteção de núcleo
        return (0.45, 0.22, 0.10, 0.13, 0.10)
    if perfil == "agressivo":
        # confia mais na memória 14/15, mas mantém proteção
        return (0.50, 0.12, 0.25, 0.05, 0.08)
    # balanceado
    if perfil == "balanceado":
        return (0.45, 0.22, 0.10, 0.13, 0.10)
    # fallback
    return (0.50, 0.18, 0.15, 0.10, 0.07)


def build_core_c(context: Dict[str, Any], janela: int = 120) -> List[int]:
    historico = context.get("historico_recente") or []
    recent = historico[-int(janela):] if historico else []
    coocc: Dict[Tuple[int, int], int] = {}
    for jogo in recent:
        for i in range(len(jogo)):
            for j in range(i + 1, len(jogo)):
                key = tuple(sorted((jogo[i], jogo[j])))
                coocc[key] = coocc.get(key, 0) + 1
    score_map: Dict[int, int] = {}
    for (a, b), score in coocc.items():
        score_map[a] = score_map.get(a, 0) + score
        score_map[b] = score_map.get(b, 0) + score
    ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    return [d for d, _ in ranked[:5]]


def ran_penalty(
    jogo: List[int],
    core_a: List[int],
    core_b: List[int],
    core_c: List[int],
) -> float:
    hit_a = len(set(jogo) & set(core_a))
    hit_b = len(set(jogo) & set(core_b))
    hit_c = len(set(jogo) & set(core_c))
    penalty = 0.0
    if hit_a < 4:
        penalty += 0.45
    if hit_b < 8:
        penalty += 0.30
    if hit_c < 3:
        penalty += 0.15
    return min(0.9, penalty)


def passa_RAN(
    jogo: List[int],
    core_a: List[int],
    core_b: List[int],
    core_c: List[int],
    limiar: float = 0.6,
) -> bool:
    return ran_penalty(jogo, core_a, core_b, core_c) < float(limiar)


def compact_game(
    jogo: List[int],
    target_size: int,
    core_a: List[int],
    core_b: List[int],
    core_c: List[int],
    freq: Dict[int, int],
    pair_scores: Dict[Tuple[int, int], int],
) -> List[int]:
    jogo_atual = sorted(set(jogo))
    while len(jogo_atual) > target_size:
        costs: List[Tuple[float, int]] = []
        for d in jogo_atual:
            in_a = 1.0 if d in core_a else 0.0
            in_b = 0.8 if d in core_b else 0.0
            in_c = 0.6 if d in core_c else 0.0
            centrality = float(freq.get(d, 0)) / max(1, max(freq.values()) if freq else 1)
            pair_score = 0.0
            for other in jogo_atual:
                if other == d:
                    continue
                key = tuple(sorted((d, other)))
                pair_score += pair_scores.get(key, 0)
            cost = (2.0 * in_a) + (1.2 * in_b) + (1.0 * in_c) + (0.6 * centrality) + (0.4 * pair_score)
            costs.append((cost, d))
        costs.sort(key=lambda x: x[0])
        _, remove_d = costs[0]
        jogo_atual.remove(remove_d)
    return sorted(jogo_atual)


def compactar_por_custo(
    jogo: List[int],
    target_size: int,
    core_a: List[int],
    core_b: List[int],
    core_c: List[int],
    freq: Dict[int, int],
    pair_scores: Dict[Tuple[int, int], int],
) -> List[int]:
    """
    Wrapper mantido por compatibilidade (mesma ideia do compact_game).
    """
    return compact_game(jogo, target_size, core_a, core_b, core_c, freq, pair_scores)


# ==========================
# Geração para um tamanho
# ==========================
def generate_for_size(
    conn: sqlite3.Connection,
    size: int,
    qtd: int,
    qtd_strong: int,
    base_size: int,
    janela: int,
    per_brain: int,
    top_n: int,
    max_sim: float,
    perfil: str,
    salvar_db: bool,
    exploration_rate: float,
    max_brain_share: float,
    ran_strict: bool,
    ensemble_bonus: float,
    quota_enabled: bool,
    quota_max_per_brain: int,
    consensus_enabled: bool,
    consensus_bonus: float,
    consensus_min_votes: int,
) -> Path:
    ultimo_concurso = fetch_max_concurso(conn)
    proximo_concurso = ultimo_concurso + 1

    context = build_context(conn, concurso_n=ultimo_concurso, janela_recente=janela)
    freq = context.get("freq_recente", {}) or {}
    memoria_1415 = fetch_memoria_top(conn, min_pontos=14, limit=500)

    core_a = [6, 7, 12, 18, 23]
    core_b = [1, 4, 5, 9, 13, 17, 20, 21, 22, 25]
    core_c = build_core_c(context, janela=120)

    pair_scores: Dict[Tuple[int, int], int] = {}
    historico = context.get("historico_recente") or []
    for jogo_hist in historico[-120:]:
        for i in range(len(jogo_hist)):
            for j in range(i + 1, len(jogo_hist)):
                key = tuple(sorted((jogo_hist[i], jogo_hist[j])))
                pair_scores[key] = pair_scores.get(key, 0) + 1

    hub = BrainHub(
        conn,
        exploration_rate=exploration_rate,
        max_brain_share=max_brain_share,
        quota_enabled=quota_enabled,
        quota_max_per_brain=quota_max_per_brain,
        consensus_enabled=consensus_enabled,
        consensus_bonus=consensus_bonus,
        consensus_min_votes=consensus_min_votes,
    )

    loaded = register_brains_auto(conn, hub)
    if not loaded:
        raise RuntimeError("Nenhum cérebro foi carregado. Verifique seus arquivos em training/brains.")

    hub.load_all()

    candidatos = hub.generate_games(
        context=context,
        size=base_size,
        per_brain=per_brain,
        top_n=top_n,
    )
    if not candidatos:
        raise RuntimeError("Hub não gerou candidatos.")

    w_hub, w_freq, w_mem, w_shape, w_ran = get_profile_weights(perfil)

    # Para bônus de “ensemble” (mesmo jogo aparecendo em múltiplos cérebros)
    jogo_counts: Dict[Tuple[int, ...], int] = {}
    brain_dist_pos_quota = Counter(c.get("brain_id", "unknown") for c in candidatos)

    compacted_candidates = 0
    for c in candidatos:
        jogo_raw = tuple(sorted(int(x) for x in c["jogo"]))
        if base_size != size:
            jogo_raw = tuple(compactar_por_custo(list(jogo_raw), size, core_a, core_b, core_c, freq, pair_scores))
            compacted_candidates += 1
        jogo_counts[jogo_raw] = jogo_counts.get(jogo_raw, 0) + 1

    ranked: List[Dict[str, Any]] = []
    ran_cortados = 0

    for c in candidatos:
        jogo = [int(x) for x in c["jogo"]]
        if base_size != size:
            # Mantém a mesma “linha” do código original (as duas chamadas)
            jogo = compactar_por_custo(jogo, size, core_a, core_b, core_c, freq, pair_scores)
            jogo = compact_game(jogo, size, core_a, core_b, core_c, freq, pair_scores)

        s_hub = float(c.get("score", 0.0))
        s_freq = score_freq_recente(jogo, freq)
        s_mem = score_memoria(jogo, memoria_1415)
        s_shape = score_shape(jogo, size)
        s_ran = ran_penalty(jogo, core_a, core_b, core_c)

        if ran_strict and not passa_RAN(jogo, core_a, core_b, core_c):
            ran_cortados += 1
        if ran_strict and s_ran >= 0.6:
            continue

        jogo_key = tuple(sorted(jogo))
        bonus = float(ensemble_bonus) if jogo_counts.get(jogo_key, 0) >= 2 else 0.0

        score_final = (
            (w_hub * s_hub)
            + (w_freq * s_freq)
            + (w_mem * s_mem)
            + (w_shape * s_shape)
            - (w_ran * s_ran)
            + bonus
        )

        ranked.append(
            {
                "jogo": sorted(jogo),
                "score_final": float(score_final),
                "score_hub": float(s_hub),
                "score_freq": float(s_freq),
                "score_mem": float(s_mem),
                "score_shape": float(s_shape),
                "score_ran": float(s_ran),
                "score_ensemble": float(bonus),
                "brain_id": str(c.get("brain_id", "unknown")),
            }
        )

    ranked.sort(key=lambda x: x["score_final"], reverse=True)
    final = diversify_ranked(ranked, top_k=qtd, max_sim=max_sim)
    strongest = ranked[: max(0, int(qtd_strong))]

    compacted_15 = 0
    if base_size != size and size == 15:
        compacted_15 = len(final)

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
    lines.append(f"Tamanho base (compactação): {base_size}")
    lines.append(f"Cérebros ativos: {len(loaded)}")
    lines.append(f"Perfil: {perfil}")
    lines.append(f"Pesos: hub={w_hub} freq={w_freq} mem={w_mem} shape={w_shape}")
    lines.append(f"Janela (contexto): {janela}")
    lines.append(f"Candidatos por cérebro: {per_brain}")
    lines.append(f"Top_n pós-hub: {top_n}")
    lines.append(f"Diversidade max_sim (Jaccard): {max_sim}")
    if quota_enabled:
        lines.append(f"Quota ativa: max_per_brain={quota_max_per_brain}")
    if consensus_enabled:
        lines.append(f"Consenso ativo: bonus={consensus_bonus} min_votos={consensus_min_votes}")
    if strongest:
        lines.append(f"Jogos fortes extras: {len(strongest)}")
    lines.append("=========================================\n")

    print(f"\n✅ Jogos finais (priorizados) — size={size} | perfil={perfil}\n")
    for i, item in enumerate(final, 1):
        jogo = item["jogo"]
        print(f"JOGO {i:02d}: {jogo} | score={item['score_final']:.4f} | fonte={item['brain_id']}")

        lines.append(f"JOGO {i:02d}: {jogo}")
        lines.append(
            f"  score_final={item['score_final']:.6f} | hub={item['score_hub']:.6f} | "
            f"freq={item['score_freq']:.6f} | mem={item['score_mem']:.6f} | shape={item['score_shape']:.6f} | "
            f"ran={item['score_ran']:.6f} | ensemble={item['score_ensemble']:.6f} | "
            f"fonte={item['brain_id']}"
        )
        lines.append("")

    if strongest:
        lines.append("=========================================")
        lines.append("🔥 JOGOS FORTES (TOP SCORE HUB)")
        lines.append("=========================================\n")
        for i, item in enumerate(strongest, 1):
            jogo = item["jogo"]
            print(f"FORTE {i:02d}: {jogo} | score={item['score_final']:.4f} | fonte={item['brain_id']}")
            lines.append(f"FORTE {i:02d}: {jogo}")
            lines.append(
                f"  score_final={item['score_final']:.6f} | hub={item['score_hub']:.6f} | "
                f"freq={item['score_freq']:.6f} | mem={item['score_mem']:.6f} | shape={item['score_shape']:.6f} | "
                f"ran={item['score_ran']:.6f} | ensemble={item['score_ensemble']:.6f} | "
                f"fonte={item['brain_id']}"
            )
            lines.append("")

    lines.append("Observação importante:")
    lines.append("- Loteria é aleatória. Este ranking só prioriza candidatos segundo o aprendizado do sistema.")
    lines.append("- Use com responsabilidade e dentro do seu orçamento.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")

    meta_path = reports_dir / f"proximo_concurso_{proximo_concurso}_jogos_{size}_meta.json"
    meta_payload = {
        "timestamp": now_str(),
        "size": size,
        "base_size": base_size,
        "ran_cortados": ran_cortados,
        "compactados_15": compacted_15,
        "compactados_candidatos": compacted_candidates,
        "brain_distribution_pos_quota": dict(brain_dist_pos_quota),
        "quota_enabled": quota_enabled,
        "quota_max_per_brain": quota_max_per_brain,
        "consensus_enabled": consensus_enabled,
        "consensus_bonus": consensus_bonus,
        "consensus_min_votes": consensus_min_votes,
    }
    meta_path.write_text(json.dumps(meta_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if salvar_db:
        ensure_pred_table(conn)
        inseridos = 0
        for ordem, item in enumerate(final, 1):
            ok = insert_pred(
                conn=conn,
                concurso_previsto=proximo_concurso,
                tamanho=size,
                ordem=ordem,
                dezenas=item["jogo"],
                score_final=item["score_final"],
                score_hub=item["score_hub"],
                score_freq=item["score_freq"],
                score_mem=item["score_mem"],
                score_shape=item["score_shape"],
                perfil=perfil,
                janela=janela,
                per_brain=per_brain,
                top_n=top_n,
                max_sim=max_sim,
                brains_ativos=len(loaded),
            )
            if ok:
                inseridos += 1
        log(f"💾 Predições salvas em DB: {inseridos}/{len(final)} (tabela predicoes_proximo)")

    log(f"📄 Relatório salvo em: {out_path}")
    return out_path


# ==========================
# MAIN
# ==========================
def main() -> None:
    parser = argparse.ArgumentParser(description="Gerar jogos para o próximo concurso usando BrainHub + memória + contexto.")
    parser.add_argument("--size", type=int, default=15, help="Tamanho do jogo principal (15, 16, 18 ou 19).")
    parser.add_argument("--qtd", type=int, default=10, help="Quantidade de jogos finais do tamanho principal.")
    parser.add_argument("--qtd-strong", type=int, default=1, help="Quantidade de jogos fortes extras (top score).")
    parser.add_argument("--second-size", type=int, default=None, help="Segundo tamanho opcional (15, 16, 18 ou 19).")
    parser.add_argument("--second-qtd", type=int, default=None, help="Quantidade de jogos do segundo tamanho.")
    parser.add_argument("--base-size", type=int, default=None, help="Tamanho base para compactação (ex: 19).")
    parser.add_argument("--janela", type=int, default=300, help="Janela de histórico para contexto.")
    parser.add_argument("--per-brain", type=int, default=120, help="Candidatos por cérebro.")
    parser.add_argument("--top-n", type=int, default=250, help="Top candidatos após BrainHub (antes do re-ranking).")
    parser.add_argument("--max-sim", type=float, default=0.78, help="Diversidade (Jaccard máximo entre jogos finais).")
    parser.add_argument("--exploration-rate", type=float, default=0.10, help="Taxa de exploração do BrainHub.")
    parser.add_argument("--max-brain-share", type=float, default=0.4, help="Limite de participação por cérebro no Top N.")
    parser.add_argument("--ran-strict", action="store_true", help="Descartar jogos com RAN alto (proteção de núcleo).")
    parser.add_argument("--ensemble-bonus", type=float, default=0.02, help="Bônus quando o jogo aparece em 2+ cérebros.")
    parser.add_argument("--quota-enabled", action="store_true", help="Ativar quota por cérebro no Top N.")
    parser.add_argument("--quota-max-per-brain", type=int, default=0, help="Limite absoluto por cérebro no Top N.")
    parser.add_argument("--consensus-enabled", action="store_true", help="Ativar bônus por consenso entre cérebros.")
    parser.add_argument("--consensus-bonus", type=float, default=0.02, help="Bônus por consenso de candidatos.")
    parser.add_argument("--consensus-min-votes", type=int, default=2, help="Mínimo de votos para bônus de consenso.")
    parser.add_argument("--perfil", type=str, default="balanceado", choices=["conservador", "balanceado", "agressivo"])
    parser.add_argument("--salvar-db", action="store_true", help="Salvar jogos gerados na tabela predicoes_proximo.")
    parser.add_argument("--seed", type=int, default=None, help="Seed para reprodutibilidade (opcional).")
    args = parser.parse_args()

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

        log("=========================================")
        log("🎯 GERADOR — PRÓXIMO CONCURSO (BrainHub)")
        log("=========================================")
        log(f"📌 DB: {Path(DB_PATH)}")
        log(f"📌 Último concurso no DB : {ultimo_concurso}")
        log(f"📌 Próximo concurso      : {ultimo_concurso + 1}")
        log("=========================================")

        size = int(args.size)
        if size not in (15, 16, 18, 19):
            size = 15

        base_size = int(args.base_size) if args.base_size is not None else size
        if base_size not in (15, 16, 18, 19):
            base_size = size

        generate_for_size(
            conn=conn,
            size=size,
            qtd=max(1, int(args.qtd)),
            qtd_strong=max(0, int(args.qtd_strong)),
            base_size=base_size,
            janela=max(50, int(args.janela)),
            per_brain=max(10, int(args.per_brain)),
            top_n=max(50, int(args.top_n)),
            max_sim=float(args.max_sim),
            perfil=str(args.perfil),
            salvar_db=bool(args.salvar_db),
            exploration_rate=float(args.exploration_rate),
            max_brain_share=float(args.max_brain_share),
            ran_strict=bool(args.ran_strict),
            ensemble_bonus=float(args.ensemble_bonus),
            quota_enabled=bool(args.quota_enabled),
            quota_max_per_brain=max(0, int(args.quota_max_per_brain)),
            consensus_enabled=bool(args.consensus_enabled),
            consensus_bonus=float(args.consensus_bonus),
            consensus_min_votes=max(2, int(args.consensus_min_votes)),
        )

        if args.second_size is not None and args.second_qtd is not None:
            second_size = int(args.second_size)
            if second_size not in (15, 16, 18, 19):
                second_size = 18

            generate_for_size(
                conn=conn,
                size=second_size,
                qtd=max(1, int(args.second_qtd)),
                qtd_strong=0,
                base_size=base_size,
                janela=max(50, int(args.janela)),
                per_brain=max(10, int(args.per_brain)),
                top_n=max(50, int(args.top_n)),
                max_sim=float(args.max_sim),
                perfil=str(args.perfil),
                salvar_db=bool(args.salvar_db),
                exploration_rate=float(args.exploration_rate),
                max_brain_share=float(args.max_brain_share),
                ran_strict=bool(args.ran_strict),
                ensemble_bonus=float(args.ensemble_bonus),
                quota_enabled=bool(args.quota_enabled),
                quota_max_per_brain=max(0, int(args.quota_max_per_brain)),
                consensus_enabled=bool(args.consensus_enabled),
                consensus_bonus=float(args.consensus_bonus),
                consensus_min_votes=max(2, int(args.consensus_min_votes)),
            )
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
