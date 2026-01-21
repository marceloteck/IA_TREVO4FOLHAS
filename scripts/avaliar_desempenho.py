from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
        self.contagens[acertos] += 1

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


def build_hub(conn, exploration_rate: float) -> BrainHub:
    hub = BrainHub(conn, exploration_rate=exploration_rate)
    hub.register(_instantiate_brain(StatFreqGlobalBrain, conn))
    hub.register(_instantiate_brain(StatFreqRecenteBrain, conn, janela=120))
    hub.register(_instantiate_brain(TemporalAtrasoBrain, conn))
    hub.register(_instantiate_brain(StatNucleoSatelitesBrain, conn, janela=300))
    hub.register(_instantiate_brain(ExplorTotalDezenasAutoBrain, conn))
    hub.register(_instantiate_brain(StatEliteMemoryBrain, conn))
    hub.register(_instantiate_brain(StatParidadeFaixasBrain, conn))
    hub.register(_instantiate_brain(StructuralPatternShapeBrain, conn))
    for brain in build_heuristic_brains(conn):
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
        concursos = [c for c in concursos if c >= inicio]
    if fim is not None:
        concursos = [c for c in concursos if c <= fim]
    if max_concursos > 0 and len(concursos) > max_concursos:
        concursos = concursos[-max_concursos:]
    return concursos


def avaliar(
    conn,
    janela: int,
    candidatos_por_cerebro: int,
    top_n: int,
    avaliar_top_k: int,
    exploration_rate: float,
    simular_aprendizado: bool,
    concursos: List[int],
) -> Dict[str, Any]:
    resultados = {15: ResultadoTipo(), 18: ResultadoTipo()}
    distribuicao = {15: Counter(), 18: Counter()}
    brains_rank = defaultdict(int)

    hub = build_hub(conn, exploration_rate=exploration_rate)

    for concurso_n in concursos:
        resultado_n1 = _fetch_result(conn, concurso_n + 1)
        if not resultado_n1:
            continue

        context = _build_context(conn, concurso_n=concurso_n, janela_recente=janela)

        for tamanho in (15, 18):
            candidatos = hub.generate_games(
                context=context,
                size=tamanho,
                per_brain=candidatos_por_cerebro,
                top_n=top_n,
            )
            avaliados = _rank_and_select(candidatos, resultado_n1, avaliar_top_k, tipo=tamanho)
            if not avaliados:
                continue
            melhor = avaliados[0]
            acertos = int(melhor["acertos"])
            resultados[tamanho].registrar(acertos)
            distribuicao[tamanho][acertos] += 1
            brains_rank[str(melhor["brain_id"])] += 1

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

    resumo = {}
    for tamanho, data in resultados.items():
        resumo[tamanho] = {
            "total": data.total,
            "media_acertos": round(data.media(), 4),
            "melhor": data.melhor,
            "contagens": dict(data.contagens),
            "q11+": sum(v for k, v in data.contagens.items() if k >= 11),
            "q12+": sum(v for k, v in data.contagens.items() if k >= 12),
            "q13+": sum(v for k, v in data.contagens.items() if k >= 13),
            "q14+": sum(v for k, v in data.contagens.items() if k >= 14),
            "q15+": sum(v for k, v in data.contagens.items() if k >= 15),
        }

    return {
        "timestamp": now_str(),
        "janela": janela,
        "candidatos_por_cerebro": candidatos_por_cerebro,
        "top_n": top_n,
        "avaliar_top_k": avaliar_top_k,
        "exploration_rate": exploration_rate,
        "simular_aprendizado": simular_aprendizado,
        "resumo": resumo,
        "brains_top1": dict(sorted(brains_rank.items(), key=lambda x: x[1], reverse=True)),
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

    if args.db_path:
        base_path = Path(args.db_path)
    else:
        base_conn = get_conn()
        db_info = base_conn.execute("PRAGMA database_list").fetchone()
        base_path = Path(db_info[2]) if db_info and db_info[2] else Path("data/BD/lotofacil.db")
        base_conn.close()

    if args.simular_aprendizado:
        tmp_path = Path("reports") / f"lotofacil_tmp_{int(datetime.now().timestamp())}.db"
        clone_db(base_path, tmp_path)
        conn = get_conn(str(tmp_path))
    else:
        conn = get_conn(str(base_path) if args.db_path else None)

    concursos = _fetch_all_concursos(conn)
    if len(concursos) < 2:
        raise SystemExit("Banco possui poucos concursos para avaliação.")

    concursos = concursos[:-1]
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
    )

    print(json.dumps(resultado, indent=2, ensure_ascii=False))

    if args.salvar_relatorio:
        path = Path(args.salvar_relatorio)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
