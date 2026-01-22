from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub
from training.trainer_v2 import (
    _build_context,
    _fetch_all_concursos,
    _fetch_result,
    _instantiate_brain,
    _rank_and_select,
)

from training.brains.statistical.freq_global_brain import StatFreqGlobalBrain
from training.brains.statistical.freq_recente_brain import StatFreqRecenteBrain
from training.brains.temporal.atraso_brain import TemporalAtrasoBrain
from training.brains.statistical.nucleo_satelites_brain import StatNucleoSatelitesBrain
from training.brains.exploratory.total_dezenas_auto_brain import ExplorTotalDezenasAutoBrain
from training.brains.statistical.elite_memory_brain import StatEliteMemoryBrain
from training.brains.statistical.paridade_faixas_brain import StatParidadeFaixasBrain
from training.brains.structural.pattern_shape_brain import StructuralPatternShapeBrain
from training.brains.heuristic.heuristic_brains import build_heuristic_brains


@dataclass
class ResultadoTipo:
    total: int = 0
    soma_acertos: int = 0
    melhor: int = 0
    contagens: Counter[int] = None

    def __post_init__(self) -> None:
        if self.contagens is None:
            self.contagens = Counter()

    def registrar(self, acertos: int) -> None:
        self.total += 1
        self.soma_acertos += acertos
        self.melhor = max(self.melhor, acertos)
        self.contagens[int(acertos)] += 1

    def media(self) -> float:
        if self.total == 0:
            return 0.0
        return float(self.soma_acertos) / float(self.total)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clone_db(orig_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(orig_path)) as src, sqlite3.connect(str(dest_path)) as dst:
        src.backup(dst)


def build_hub(
    conn,
    exploration_rate: float,
    quota_enabled: bool,
    quota_max_per_brain: int,
    consensus_enabled: bool,
    consensus_bonus: float,
    consensus_min_votes: int,
    heuristic_limit: Optional[int],
    disable_heuristics: bool,
    disable_structural: bool,
) -> BrainHub:
    hub = BrainHub(
        conn,
        exploration_rate=float(exploration_rate),
        quota_enabled=bool(quota_enabled),
        quota_max_per_brain=int(quota_max_per_brain),
        consensus_enabled=bool(consensus_enabled),
        consensus_bonus=float(consensus_bonus),
        consensus_min_votes=int(consensus_min_votes),
    )

    # Base
    hub.register(_instantiate_brain(StatFreqGlobalBrain, conn))
    hub.register(_instantiate_brain(StatFreqRecenteBrain, conn, janela=120))
    hub.register(_instantiate_brain(TemporalAtrasoBrain, conn))
    hub.register(_instantiate_brain(StatNucleoSatelitesBrain, conn, janela=300))
    hub.register(_instantiate_brain(ExplorTotalDezenasAutoBrain, conn))
    hub.register(_instantiate_brain(StatEliteMemoryBrain, conn))
    hub.register(_instantiate_brain(StatParidadeFaixasBrain, conn))

    # Structural (opcional)
    if not disable_structural:
        hub.register(_instantiate_brain(StructuralPatternShapeBrain, conn))

    # Heuristics (opcional)
    if not disable_heuristics:
        heuristics = build_heuristic_brains(conn)
        if heuristic_limit is not None and int(heuristic_limit) >= 0:
            heuristics = heuristics[: int(heuristic_limit)]
        for brain in heuristics:
            hub.register(brain)

    hub.load_all()
    return hub


def selecionar_concursos(
    concursos: List[int],
    inicio: Optional[int],
    fim: Optional[int],
    max_concursos: int,
) -> List[int]:
    if not concursos:
        return []
    if inicio is not None:
        concursos = [c for c in concursos if c >= int(inicio)]
    if fim is not None:
        concursos = [c for c in concursos if c <= int(fim)]
    if max_concursos > 0 and len(concursos) > int(max_concursos):
        concursos = concursos[-int(max_concursos):]
    return concursos


def _brain_metrics() -> Dict[str, Dict[str, Any]]:
    return defaultdict(
        lambda: {
            "generated_15": 0,
            "generated_18": 0,
            "top1_15": 0,
            "top1_18": 0,
            "topk_sum_15": 0,
            "topk_count_15": 0,
            "topk_best_15": 0,
            "topk_sum_18": 0,
            "topk_count_18": 0,
            "topk_best_18": 0,
        }
    )


def avaliar(
    conn,
    janela: int,
    candidatos_por_cerebro: int,
    top_n: int,
    avaliar_top_k: int,
    exploration_rate: float,
    simular_aprendizado: bool,
    concursos: List[int],
    quota_enabled: bool,
    quota_max_per_brain: int,
    consensus_enabled: bool,
    consensus_bonus: float,
    consensus_min_votes: int,
    heuristic_limit: Optional[int],
    disable_heuristics: bool,
    disable_structural: bool,
) -> Dict[str, Any]:
    resultados = {15: ResultadoTipo(), 18: ResultadoTipo()}
    distribuicao = {15: Counter(), 18: Counter()}
    brains_rank = defaultdict(int)
    brains_stats = _brain_metrics()

    hub = build_hub(
        conn=conn,
        exploration_rate=exploration_rate,
        quota_enabled=quota_enabled,
        quota_max_per_brain=quota_max_per_brain,
        consensus_enabled=consensus_enabled,
        consensus_bonus=consensus_bonus,
        consensus_min_votes=consensus_min_votes,
        heuristic_limit=heuristic_limit,
        disable_heuristics=disable_heuristics,
        disable_structural=disable_structural,
    )

    for concurso_n in concursos:
        resultado_n1 = _fetch_result(conn, concurso_n + 1)
        if not resultado_n1:
            continue

        context = _build_context(conn, concurso_n=concurso_n, janela_recente=janela)

        for tamanho in (15, 18):
            candidatos = hub.generate_games(
                context=context,
                size=int(tamanho),
                per_brain=int(candidatos_por_cerebro),
                top_n=int(top_n),
            )

            for item in candidatos:
                key = "generated_15" if tamanho == 15 else "generated_18"
                brains_stats[str(item.get("brain_id", "unknown"))][key] += 1

            avaliados = _rank_and_select(candidatos, resultado_n1, avaliar_top_k, tipo=tamanho)
            if not avaliados:
                continue

            melhor = avaliados[0]
            acertos = int(melhor["acertos"])

            resultados[tamanho].registrar(acertos)
            distribuicao[tamanho][acertos] += 1

            melhor_brain = str(melhor.get("brain_id", "unknown"))
            brains_rank[melhor_brain] += 1

            top_key = "top1_15" if tamanho == 15 else "top1_18"
            brains_stats[melhor_brain][top_key] += 1

            for item in avaliados:
                acertos_item = int(item["acertos"])
                brain_id = str(item.get("brain_id", "unknown"))
                if tamanho == 15:
                    brains_stats[brain_id]["topk_sum_15"] += acertos_item
                    brains_stats[brain_id]["topk_count_15"] += 1
                    brains_stats[brain_id]["topk_best_15"] = max(
                        brains_stats[brain_id]["topk_best_15"],
                        acertos_item,
                    )
                else:
                    brains_stats[brain_id]["topk_sum_18"] += acertos_item
                    brains_stats[brain_id]["topk_count_18"] += 1
                    brains_stats[brain_id]["topk_best_18"] = max(
                        brains_stats[brain_id]["topk_best_18"],
                        acertos_item,
                    )

            if simular_aprendizado:
                for item in avaliados:
                    hub.learn(
                        concurso_n=concurso_n,
                        jogo=item["jogo"],
                        resultado_n1=resultado_n1,
                        pontos=item["acertos"],
                        context=context,
                        brain_id=item["brain_id"],
                    )

    resumo: Dict[int, Dict[str, Any]] = {}
    for tamanho, data in resultados.items():
        quase_acertos = sum(v for k, v in data.contagens.items() if 11 <= k <= 13)
        foco_14_15 = sum(v for k, v in data.contagens.items() if k >= 14)
        resumo[tamanho] = {
            "total": data.total,
            "media_acertos": round(data.media(), 4),
            "melhor": data.melhor,
            "contagens": dict(data.contagens),
            "quase_acertos_11_13": quase_acertos,
            "foco_14_15": foco_14_15,
            "q11+": sum(v for k, v in data.contagens.items() if k >= 11),
            "q12+": sum(v for k, v in data.contagens.items() if k >= 12),
            "q13+": sum(v for k, v in data.contagens.items() if k >= 13),
            "q14+": sum(v for k, v in data.contagens.items() if k >= 14),
            "q15+": sum(v for k, v in data.contagens.items() if k >= 15),
        }

    brains_output: Dict[str, Dict[str, Any]] = {}
    for brain_id, stats in brains_stats.items():
        avg_15 = (stats["topk_sum_15"] / stats["topk_count_15"]) if stats["topk_count_15"] > 0 else 0.0
        avg_18 = (stats["topk_sum_18"] / stats["topk_count_18"]) if stats["topk_count_18"] > 0 else 0.0
        brains_output[brain_id] = {
            "generated_15": stats["generated_15"],
            "generated_18": stats["generated_18"],
            "top1_15": stats["top1_15"],
            "top1_18": stats["top1_18"],
            "avg_acertos_topk_15": round(avg_15, 4),
            "avg_acertos_topk_18": round(avg_18, 4),
            "best_acertos_topk_15": stats["topk_best_15"],
            "best_acertos_topk_18": stats["topk_best_18"],
        }

    return {
        "timestamp": now_str(),
        "janela": int(janela),
        "candidatos_por_cerebro": int(candidatos_por_cerebro),
        "top_n": int(top_n),
        "avaliar_top_k": int(avaliar_top_k),
        "exploration_rate": float(exploration_rate),
        "quota_enabled": bool(quota_enabled),
        "quota_max_per_brain": int(quota_max_per_brain),
        "consensus_enabled": bool(consensus_enabled),
        "consensus_bonus": float(consensus_bonus),
        "consensus_min_votes": int(consensus_min_votes),
        "heuristic_limit": heuristic_limit,
        "disable_heuristics": bool(disable_heuristics),
        "disable_structural": bool(disable_structural),
        "simular_aprendizado": bool(simular_aprendizado),
        "resumo": resumo,
        "brains_top1": dict(sorted(brains_rank.items(), key=lambda x: x[1], reverse=True)),
        "brains": dict(
            sorted(
                brains_output.items(),
                key=lambda x: x[1]["top1_15"] + x[1]["top1_18"],
                reverse=True,
            )
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação de desempenho e aprendizado da IA.")
    parser.add_argument("--db-path", type=str, default=None, help="Caminho do banco lotofacil.db.")
    parser.add_argument("--janela", type=int, default=300, help="Janela de histórico recente.")
    parser.add_argument("--candidatos", type=int, default=80, help="Candidatos por cérebro.")
    parser.add_argument("--top-n", type=int, default=60, help="Top N por tamanho após diversificação.")
    parser.add_argument("--avaliar-top-k", type=int, default=40, help="Quantos candidatos avaliar.")
    parser.add_argument("--max-concursos", type=int, default=200, help="Avalia os últimos N concursos.")
    parser.add_argument("--inicio", type=int, default=None, help="Concurso inicial (inclusive).")
    parser.add_argument("--fim", type=int, default=None, help="Concurso final (inclusive).")
    parser.add_argument("--exploration-rate", type=float, default=0.08, help="Taxa de exploração do BrainHub.")
    parser.add_argument("--quota-enabled", action="store_true", help="Ativar quota por cérebro no Top N.")
    parser.add_argument("--quota-max-per-brain", type=int, default=0, help="Limite absoluto por cérebro no Top N.")
    parser.add_argument("--consensus-enabled", action="store_true", help="Ativar bônus por consenso entre cérebros.")
    parser.add_argument("--consensus-bonus", type=float, default=0.02, help="Bônus por consenso de candidatos.")
    parser.add_argument("--consensus-min-votes", type=int, default=2, help="Mínimo de votos para bônus de consenso.")
    parser.add_argument(
        "--heuristic-limit",
        type=int,
        default=None,
        help="Limitar quantidade de cérebros heurísticos usados na avaliação.",
    )
    parser.add_argument(
        "--disable-heuristics",
        action="store_true",
        help="Desativar cérebros heurísticos para reduzir custo da avaliação.",
    )
    parser.add_argument(
        "--disable-structural",
        action="store_true",
        help="Desativar cérebros estruturais para reduzir custo da avaliação.",
    )
    parser.add_argument(
        "--simular-aprendizado",
        action="store_true",
        help="Executa aprendizado em um banco temporário para medir efeito incremental.",
    )
    parser.add_argument(
        "--salvar-relatorio",
        type=str,
        default=None,
        help="Arquivo JSON para salvar o relatório.",
    )

    args = parser.parse_args()

    # Resolve DB base path (sem duplicidade)
    if args.db_path:
        base_path = Path(args.db_path)
    else:
        base_conn = get_conn()
        db_info = base_conn.execute("PRAGMA database_list").fetchone()
        base_path = Path(db_info[2]) if db_info and db_info[2] else Path("data/BD/lotofacil.db")
        base_conn.close()

    # DB de simulação (backup)
    if args.simular_aprendizado:
        tmp_path = Path("reports") / f"lotofacil_tmp_{int(datetime.now().timestamp())}.db"
        clone_db(base_path, tmp_path)
        conn = get_conn(str(tmp_path))
    else:
        conn = get_conn(str(base_path) if args.db_path else None)

    try:
        concursos = _fetch_all_concursos(conn)
        if len(concursos) < 2:
            raise SystemExit("Banco possui poucos concursos para avaliação.")

        concursos = concursos[:-1]  # não avalia o último (sem N+1)
        concursos = selecionar_concursos(concursos, args.inicio, args.fim, args.max_concursos)

        resultado = avaliar(
            conn=conn,
            janela=args.janela,
            candidatos_por_cerebro=args.candidatos,
            top_n=args.top_n,
            avaliar_top_k=args.avaliar_top_k,
            exploration_rate=args.exploration_rate,
            simular_aprendizado=args.simular_aprendizado,
            concursos=concursos,
            quota_enabled=args.quota_enabled,
            quota_max_per_brain=max(0, int(args.quota_max_per_brain)),
            consensus_enabled=args.consensus_enabled,
            consensus_bonus=float(args.consensus_bonus),
            consensus_min_votes=max(2, int(args.consensus_min_votes)),
            heuristic_limit=args.heuristic_limit,
            disable_heuristics=args.disable_heuristics,
            disable_structural=args.disable_structural,
        )

        print(json.dumps(resultado, indent=2, ensure_ascii=False))

        if args.salvar_relatorio:
            path = Path(args.salvar_relatorio)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
