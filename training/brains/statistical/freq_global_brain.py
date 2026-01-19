# training/brains/statistical/freq_global_brain.py
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List
import random

from training.core.base_brain import BaseBrain
from training.brains._utils import weighted_sample_without_replacement, count_even, max_consecutive_run


class StatFreqGlobalBrain(BaseBrain):
    """
    Cérebro estatístico: Frequência Global (N->N+1)
    - Aprende com resultado real N+1 (freq global acumulada)
    - Gera candidatos com amostragem ponderada (sem reposição)
    - Persistência total via BaseBrain (SQLite)
    """

    def __init__(self, db_conn, core_15: int = 18, core_18: int = 22):
        super().__init__(
            db_conn=db_conn,
            brain_id="stat_freq_global",
            name="Stat - Frequência Global",
            category="estatistico",
            version="v1",
        )
        self.core_15 = int(core_15)
        self.core_18 = int(core_18)

        # memória interna
        self.freq = Counter()  # numero -> contagem
        self.total_seen = 0

        # carrega estado persistido (se existir)
        self.load_state()

    # ==================================================
    # CONTEXTO
    # ==================================================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # Se ainda não aprendeu nada, relevância menor (mas não zero)
        return 0.6 if self.total_seen <= 0 else 1.0

    # ==================================================
    # GERAÇÃO
    # ==================================================
    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)

        universo = list(range(1, 26))

        # define core conforme tamanho do jogo
        core_size = self.core_15 if size == 15 else self.core_18
        core_size = max(size, min(25, core_size))

        # ranking global
        ranked = sorted(universo, key=lambda d: (self.freq.get(d, 0), -d), reverse=True)
        core = ranked[:core_size]

        # pesos (suavizados) para evitar zeros
        # quanto mais frequência, maior a chance; sempre >= 0.001
        weights = {d: float(self.freq.get(d, 0) + 1) for d in core}

        jogos: List[List[int]] = []

        for _ in range(n):
            # 70% do jogo vem do core ponderado
            k_core = max(0, min(size, int(round(size * 0.70))))
            escolhidos_core = weighted_sample_without_replacement(weights, k_core)

            jogo = set(escolhidos_core)

            # completa com diversidade do universo
            while len(jogo) < size:
                jogo.add(random.choice(universo))

            jogos.append(sorted(jogo))

        return jogos

    # ==================================================
    # SCORE INTERNO
    # ==================================================
    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0

        # normaliza por max freq (evita score explodir com o tempo)
        maxf = max(self.freq.values()) if self.freq else 1

        # score base: média de frequências normalizadas
        s_freq = sum((self.freq.get(int(d), 0) / maxf) for d in jogo) / len(jogo)

        # pequenas penalizações estruturais (leve, sem overfit)
        pares = count_even(jogo)
        run = max_consecutive_run(jogo)

        # ideal 7/8 pares em jogo de 15 (equilíbrio)
        if len(jogo) == 15:
            s_par = 1.0 - (abs(pares - 7.5) / 7.5)  # 0..1
        else:
            # para 18, alvo ~9 pares
            s_par = 1.0 - (abs(pares - 9.0) / 9.0)

        # penaliza sequências longas
        pen_seq = 0.0
        if run >= 6:
            pen_seq = 0.25
        elif run == 5:
            pen_seq = 0.15
        elif run == 4:
            pen_seq = 0.07

        # score final (comparativo)
        return (s_freq * 0.72 + s_par * 0.28) - pen_seq

    # ==================================================
    # APRENDIZADO N -> N+1
    # ==================================================
    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        # Frequência global deve refletir o que realmente saiu (resultado N+1)
        if not resultado_n1:
            return

        res = [int(x) for x in resultado_n1]
        self.freq.update(res)
        self.total_seen += len(res)

        # opcional: reforço leve baseado em pontuação (sem distorcer a frequência real)
        # se o jogo foi muito bom, aumenta um pouco o peso das dezenas do jogo
        if pontos >= 14:
            for d in jogo:
                self.freq[int(d)] += 1

        # persiste no estado (mas sem salvar em disco toda chamada se você não quiser)
        self.state["freq"] = {str(k): int(v) for k, v in self.freq.items()}
        self.state["total_seen"] = int(self.total_seen)

        # atualiza performance do cérebro por concurso (tabela cerebro_performance)
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==================================================
    # PERSISTÊNCIA (SQLite via BaseBrain)
    # ==================================================
    def save_state(self) -> None:
        # garante estado consistente
        self.state["freq"] = {str(k): int(v) for k, v in self.freq.items()}
        self.state["total_seen"] = int(self.total_seen)
        self.state["core_15"] = int(self.core_15)
        self.state["core_18"] = int(self.core_18)
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

        raw = self.state.get("freq") or {}
        self.freq = Counter({int(k): int(v) for k, v in raw.items()})

        self.total_seen = int(self.state.get("total_seen", 0))
        self.core_15 = int(self.state.get("core_15", self.core_15))
        self.core_18 = int(self.state.get("core_18", self.core_18))

    # ==================================================
    # RELATÓRIO
    # ==================================================
    def report(self) -> Dict[str, Any]:
        top10 = [n for n, _ in self.freq.most_common(10)]
        return {
            **super().report(),
            "total_seen": int(self.total_seen),
            "top10": top10,
            "core_15": int(self.core_15),
            "core_18": int(self.core_18),
        }
