# training/backtest/backtest_engine.py
from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ==========================
# Boot de path (roda de qualquer lugar)
# ==========================
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub
from training.utils.comparador import contar_acertos


# ==========================
# Config padrão (seguro pra i3/12GB)
# ==========================
DEFAULT_BLOCK_SIZE = 250
DEFAULT_SAVE_EVERY = 10
DEFAULT_MIN_MEM = 12
DEFAULT_MAX_SIM = 0.78

# Candidatos / custo
DEFAULT_PER_BRAIN_CHOICES = (60, 80, 120)
DEFAULT_TOPN_CHOICES = (80, 120, 180, 250)
DEFAULT_JANELA_CHOICES = (120, 200, 300, 500)

DEFAULT_PROFILES = ("conservador", "balanceado", "agressivo")


# ==========================
# Util
# ==========================
def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_str()}] {msg}")


def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _placeholders(n: int) -> str:
    return ",".join(["?"] * int(n))


# ==========================
# DB helpers (backtest)
# ==========================
def ensure_backtest_checkpoint(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS checkpoint_backtest (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            ultimo_concurso_processado INTEGER,
            etapa TEXT,
            timestamp TEXT
        );
        """
    )
    conn.commit()


def get_backtest_checkpoint(conn: sqlite3.Connection) -> int:
    ensure_backtest_checkpoint(conn)
    cur = conn.cursor()
    cur.execute("SELECT ultimo_concurso_processado FROM checkpoint_backtest WHERE id=1")
    row = cur.fetchone()
    if not row or row[0] is None:
        return 0
    return int(row[0])


def set_backtest_checkpoint(conn: sqlite3.Connection, ultimo: int, etapa: str = "backtest_engine") -> None:
    ensure_backtest_checkpoint(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO checkpoint_backtest (id, ultimo_concurso_processado, etapa, timestamp)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            ultimo_concurso_processado=excluded.ultimo_concurso_processado,
            etapa=excluded.etapa,
            timestamp=excluded.timestamp
        """,
        (int(ultimo), str(etapa), now_str()),
    )
    conn.commit()


def fetch_all_concursos(conn: sqlite3.Connection) -> List[int]:
    cur = conn.cursor()
    cur.execute("SELECT concurso FROM concursos ORDER BY concurso ASC")
    return [int(r[0]) for r in cur.fetchall()]


def fetch_result(conn: sqlite3.Connection, concurso: int) -> Optional[List[int]]:
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


def fetch_recent_results(conn: sqlite3.Connection, concurso_n: int, janela: int) -> List[List[int]]:
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


def build_context(conn: sqlite3.Connection, concurso_n: int, janela_recente: int) -> Dict[str, Any]:
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


def insert_tentativa(
    conn: sqlite3.Connection,
    concurso_n: int,
    concurso_n1: int,
    tipo_jogo: int,
    tentativa: int,
    dezenas: List[int],
    acertos: int,
    score: float,
    score_tag: str,
    brain_id: str,
    tempo_exec: float,
    timestamp: str,
) -> None:
    """
    Insere em 'tentativas' usando o formato d1..d18.
    BLINDADO contra mismatch de colunas/values.
    """
    dezenas_sorted = sorted(int(x) for x in dezenas if x is not None)
    payload = dezenas_sorted + [None] * (18 - len(dezenas_sorted))
    payload = payload[:18]

    cols = (
        ["concurso_n", "concurso_n1", "tipo_jogo", "tentativa"]
        + [f"d{i}" for i in range(1, 19)]
        + ["acertos", "score", "score_tag", "brain_id", "tempo_exec", "timestamp"]
    )

    values = (
        [int(concurso_n), int(concurso_n1), int(tipo_jogo), int(tentativa)]
        + payload
        + [int(acertos), float(score), str(score_tag), str(brain_id), float(tempo_exec), str(timestamp)]
    )

    sql = f"INSERT INTO tentativas ({','.join(cols)}) VALUES ({_placeholders(len(values))})"
    cur = conn.cursor()
    cur.execute(sql, tuple(values))
    conn.commit()


def insert_memoria_forte(
    conn: sqlite3.Connection,
    concurso_n: int,
    concurso_n1: int,
    tipo_jogo: int,
    dezenas: List[int],
    acertos: int,
    peso: float,
    origem: str,
    min_mem: int,
) -> bool:
    if int(acertos) < int(min_mem):
        return False

    dezenas_sorted = sorted(int(x) for x in dezenas if x is not None)
    payload = dezenas_sorted + [None] * (18 - len(dezenas_sorted))
    payload = payload[:18]

    cols = (
        ["concurso_n", "concurso_n1", "tipo_jogo"]
        + [f"d{i}" for i in range(1, 19)]
        + ["acertos", "peso", "origem", "timestamp"]
    )

    values = (
        [int(concurso_n), int(concurso_n1), int(tipo_jogo)]
        + payload
        + [int(acertos), float(peso), str(origem), now_str()]
    )

    sql = f"INSERT OR IGNORE INTO memoria_jogos ({','.join(cols)}) VALUES ({_placeholders(len(values))})"
    cur = conn.cursor()
    cur.execute(sql, tuple(values))
    conn.commit()
    return cur.rowcount > 0


# ==========================
# Registro de cérebros (auto)
# ==========================
def register_brains_auto(conn, hub: BrainHub) -> List[str]:
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
            # não explode: backtest precisa continuar mesmo se algum cérebro falhar
            pass

    def _try_add_builder(import_path: str, func_name: str, *args, **kwargs):
        nonlocal loaded
        try:
            mod = __import__(import_path, fromlist=[func_name])
            builder = getattr(mod, func_name)
            brains = builder(conn, *args, **kwargs)
            for b in brains:
                hub.register(b)
                loaded.append(getattr(b, "id", f"{import_path}.{func_name}"))
        except Exception:
            # não explode: backtest precisa continuar mesmo se algum cérebro falhar
            pass

    # Base confirmados
    _try_add("training.brains.statistical.freq_global_brain", "StatFreqGlobalBrain")
    _try_add("training.brains.statistical.freq_recente_brain", "StatFreqRecenteBrain", janela=120)
    _try_add("training.brains.temporal.atraso_brain", "TemporalAtrasoBrain")

    # Extras (se existirem no projeto)
    _try_add("training.brains.statistical.nucleo_satelites_brain", "StatNucleoSatelitesBrain")
    _try_add("training.brains.exploratory.total_dezenas_auto_brain", "ExplorTotalDezenasAutoBrain")
    _try_add("training.brains.statistical.elite_memory_brain", "StatEliteMemoryBrain")
    _try_add("training.brains.statistical.paridade_faixas_brain", "StatParidadeFaixasBrain")
    _try_add("training.brains.structural.pattern_shape_brain", "StructuralPatternShapeBrain")
    _try_add("training.brains.brain_step_sequences", "HeuristicStepSequencesBrain")
    _try_add("training.brains.structural.core_protect_brain", "StructuralCoreProtectBrain")
    _try_add("training.brains.structural.anti_absence_brain", "StructuralAntiAbsenceBrain")
    _try_add_builder("training.brains.heuristic.heuristic_brains", "build_heuristic_brains")

    return loaded


# ==========================
# Exploração (config dinâmica)
# ==========================
@dataclass
class ExploreConfig:
    janela: int
    per_brain: int
    top_n: int
    perfil: str
    drop_rate: float  # chance de desabilitar um cérebro nesta rodada
    score_tag: str


def sample_explore_config(
    janela_choices: Tuple[int, ...],
    per_brain_choices: Tuple[int, ...],
    topn_choices: Tuple[int, ...],
    profiles: Tuple[str, ...],
    score_tag_base: str,
    aggressive: bool,
) -> ExploreConfig:
    janela = random.choice(janela_choices)
    per_brain = random.choice(per_brain_choices)
    top_n = random.choice(topn_choices)
    perfil = random.choice(profiles)

    # Se aggressive=True, explora mais: mais candidatos e menor drop_rate
    if aggressive:
        per_brain = max(per_brain, 120)
        top_n = max(top_n, 180)
        drop_rate = 0.12
    else:
        drop_rate = 0.18

    score_tag = f"{score_tag_base}:{perfil}:J{janela}:P{per_brain}:T{top_n}"
    return ExploreConfig(janela=janela, per_brain=per_brain, top_n=top_n, perfil=perfil, drop_rate=drop_rate, score_tag=score_tag)


def maybe_disable_some_brains(hub: BrainHub, drop_rate: float) -> int:
    """
    Desabilita alguns cérebros aleatoriamente para explorar combinações.
    Retorna quantos ficaram ativos.
    """
    active = 0
    for b in getattr(hub, "brains", []):
        # garante atributo enabled
        if not hasattr(b, "enabled"):
            try:
                setattr(b, "enabled", True)
            except Exception:
                pass

        if random.random() < drop_rate:
            try:
                b.enabled = False
            except Exception:
                pass
        else:
            try:
                b.enabled = True
                active += 1
            except Exception:
                pass
    return active


# ==========================
# Runner de 1 concurso (N->N+1)
# ==========================
def run_one_concurso(
    conn: sqlite3.Connection,
    hub: BrainHub,
    concurso_n: int,
    cfg: ExploreConfig,
    min_mem: int,
    avaliar_top_k: int,
) -> Dict[str, int]:
    """
    Executa:
    - build_context (com cfg.janela)
    - generate 15/18
    - avalia vs resultado N+1
    - salva tentativas + memórias
    - aprende no hub
    """
    resultado_n1 = fetch_result(conn, concurso_n + 1)
    if not resultado_n1:
        return {"mem": 0, "a14": 0, "a15": 0}

    context = build_context(conn, concurso_n, cfg.janela)

    # ✅ RUN_TAG definido (corrige NameError)
    RUN_TAG = str(cfg.score_tag)

    t0 = time.time()
    cand15 = hub.generate_games(context=context, size=15, per_brain=cfg.per_brain, top_n=cfg.top_n)
    cand18 = hub.generate_games(context=context, size=18, per_brain=cfg.per_brain, top_n=cfg.top_n)
    tempo_exec = time.time() - t0

    # avalia apenas top K candidatos (controle de custo)
    cand15 = (cand15 or [])[: int(avaliar_top_k)]
    cand18 = (cand18 or [])[: int(avaliar_top_k)]

    mem = a14 = a15 = 0
    tentativa = 1

    def _process(cands: List[Dict[str, Any]], tipo: int):
        nonlocal mem, a14, a15, tentativa

        tipo = int(tipo)

        for c in cands:
            jogo = [int(x) for x in c.get("jogo", []) if x is not None]

            if len(jogo) < 15:
                continue

            jogo = sorted(set(jogo))

            # força exatamente 15/18
            if tipo in (15, 18) and len(jogo) != tipo:
                if len(jogo) > tipo:
                    jogo = jogo[:tipo]
                else:
                    continue

            acertos = contar_acertos(jogo, resultado_n1)
            score = float(c.get("score", 0.0))
            brain_id = str(c.get("brain_id", "unknown"))

            insert_tentativa(
                conn=conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                tentativa=tentativa,
                dezenas=jogo,
                acertos=acertos,
                score=score,
                score_tag=RUN_TAG,      # ✅ agora existe
                brain_id=brain_id,
                tempo_exec=tempo_exec,
                timestamp=now_str(),
            )

            if insert_memoria_forte(
                conn=conn,
                concurso_n=concurso_n,
                concurso_n1=concurso_n + 1,
                tipo_jogo=tipo,
                dezenas=jogo,
                acertos=acertos,
                peso=1.0,
                origem=f"{cfg.score_tag}:{brain_id}",
                min_mem=min_mem,
            ):
                mem += 1

            if acertos >= 14:
                a14 += 1
            if acertos == 15:
                a15 += 1

            hub.learn(
                concurso_n=concurso_n,
                jogo=jogo,
                resultado_n1=resultado_n1,
                pontos=acertos,
                context=context,
                brain_id=brain_id,
            )

            tentativa += 1

    _process(cand15, 15)
    _process(cand18, 18)

    return {"mem": mem, "a14": a14, "a15": a15}


# ==========================
# Main loop (infinito por tempo/blocos)
# ==========================
def main() -> None:
    p = argparse.ArgumentParser(description="Backtest/Exploração infinito N->N+1 (replay do passado) com persistência no BD.")
    p.add_argument("--minutes", type=int, default=0, help="Rodar por X minutos (0 desliga).")
    p.add_argument("--hours", type=float, default=0.0, help="Rodar por X horas (0 desliga).")
    p.add_argument("--steps", type=int, default=0, help="Rodar por X concursos processados (0 desliga).")
    p.add_argument("--block-size", type=int, default=DEFAULT_BLOCK_SIZE, help="Tamanho do bloco por ciclo (circular).")
    p.add_argument("--save-every", type=int, default=DEFAULT_SAVE_EVERY, help="Salvar estados do hub a cada N concursos.")
    p.add_argument("--min-mem", type=int, default=DEFAULT_MIN_MEM, help="Salvar memoria_jogos a partir deste valor.")
    p.add_argument("--avaliar-top-k", type=int, default=40, help="Quantos candidatos avaliar por tamanho (15 e 18).")
    p.add_argument("--seed", type=int, default=None, help="Seed (opcional).")
    p.add_argument("--aggressive", action="store_true", help="Exploração mais pesada (mais candidatos).")
    args = p.parse_args()

    if args.seed is not None:
        random.seed(int(args.seed))

    run_seconds = 0.0
    if args.hours and args.hours > 0:
        run_seconds = float(args.hours) * 3600.0
    elif args.minutes and args.minutes > 0:
        run_seconds = float(args.minutes) * 60.0

    max_steps = int(args.steps) if args.steps and args.steps > 0 else 0

    conn = get_conn()
    try:
        if not safe_table_exists(conn, "concursos"):
            raise RuntimeError("Tabela 'concursos' não existe. Rode START/startBD.py.")

        concursos = fetch_all_concursos(conn)
        if len(concursos) < 2:
            raise RuntimeError("Poucos concursos no banco. Precisa ter N e N+1.")

        ultimo_treinavel = concursos[-2]  # precisa existir N+1

        ensure_backtest_checkpoint(conn)
        ck = get_backtest_checkpoint(conn)

        # Se checkpoint inválido, começa do início
        if ck < concursos[0] or ck > ultimo_treinavel:
            ck = 0

        log("=========================================")
        log("🔁 BACKTEST ENGINE — EXPLORAÇÃO INFINITA")
        log("=========================================")
        log(f"📌 Último treinável (N) : {ultimo_treinavel}")
        log(f"📌 Checkpoint backtest  : {ck}")
        log(f"📌 block_size           : {int(args.block_size)}")
        log(f"📌 save_every           : {int(args.save_every)}")
        log(f"📌 avaliar_top_k        : {int(args.avaliar_top_k)}")
        if run_seconds > 0:
            log(f"⏱️ Modo tempo            : {run_seconds:.0f}s")
        if max_steps > 0:
            log(f"🔢 Modo steps            : {max_steps} concursos")
        log("=========================================")

        hub = BrainHub(conn)
        loaded = register_brains_auto(conn, hub)
        if not loaded:
            raise RuntimeError("Nenhum cérebro foi carregado. Verifique seus arquivos em training/brains.")

        hub.load_all()

        # ciclo circular
        start_time = time.time()
        steps_done = 0
        total_mem = total_14 = total_15 = 0

        # monta lista de N treináveis
        trainable = [c for c in concursos if c <= ultimo_treinavel]

        # encontra posição do checkpoint
        if ck == 0:
            pos = 0
        else:
            try:
                pos = trainable.index(ck) + 1
            except ValueError:
                pos = 0

        while True:
            # condições de parada
            if run_seconds > 0 and (time.time() - start_time) >= run_seconds:
                break
            if max_steps > 0 and steps_done >= max_steps:
                break

            # seleciona bloco circular
            block: List[int] = []
            for _ in range(max(1, int(args.block_size))):
                if pos >= len(trainable):
                    pos = 0
                block.append(int(trainable[pos]))
                pos += 1

            # cada bloco usa uma configuração exploratória diferente
            cfg = sample_explore_config(
                janela_choices=tuple(DEFAULT_JANELA_CHOICES),
                per_brain_choices=tuple(DEFAULT_PER_BRAIN_CHOICES),
                topn_choices=tuple(DEFAULT_TOPN_CHOICES),
                profiles=tuple(DEFAULT_PROFILES),
                score_tag_base="backtest_v1",
                aggressive=bool(args.aggressive),
            )

            active = maybe_disable_some_brains(hub, drop_rate=cfg.drop_rate)
            log(f"🧪 Nova rodada: {cfg.score_tag} | brains_ativos={active}/{len(loaded)}")

            for i, concurso_n in enumerate(block, 1):
                if run_seconds > 0 and (time.time() - start_time) >= run_seconds:
                    break
                if max_steps > 0 and steps_done >= max_steps:
                    break

                stats = run_one_concurso(
                    conn=conn,
                    hub=hub,
                    concurso_n=int(concurso_n),
                    cfg=cfg,
                    min_mem=int(args.min_mem),
                    avaliar_top_k=int(args.avaliar_top_k),
                )

                total_mem += int(stats["mem"])
                total_14 += int(stats["a14"])
                total_15 += int(stats["a15"])

                steps_done += 1
                set_backtest_checkpoint(conn, int(concurso_n), etapa="backtest_engine")

                if steps_done % max(1, int(args.save_every)) == 0:
                    hub.save_all()

                if i % 25 == 0:
                    log(
                        f"↪ progresso bloco: {i}/{len(block)} | steps={steps_done} | "
                        f"mem+={total_mem} | 14+={total_14} | 15={total_15}"
                    )

            # salva no final de cada bloco
            hub.save_all()

        dur = time.time() - start_time
        log("=========================================")
        log("✅ BACKTEST ENGINE FINALIZADO")
        log("=========================================")
        log(f"⏱️ Duração total  : {dur:.2f}s")
        log(f"🔢 Steps          : {steps_done}")
        log(f"💾 Memórias (>=min_mem): {total_mem}")
        log(f"🔥 14+            : {total_14}")
        log(f"🏆 15             : {total_15}")
        log(f"📌 checkpoint_bt  : {get_backtest_checkpoint(conn)}")
        log("=========================================")

    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
