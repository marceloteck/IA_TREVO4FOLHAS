# training/brains/statistical/freq_global_brain.py
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List
import random

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement


class StatFreqGlobalBrain(BaseBrain):
    """
    stat_freq_global
    - Aprende a frequência GLOBAL das dezenas com base nos RESULTADOS REAIS (N+1)
    - Pode dar reforço leve quando um jogo gerado performa muito bem (14/15)
    - Gera jogos por amostragem ponderada (sem reposição) + exploração controlada
    """

    def __init__(self, db_conn):
        super().__init__(
            db_conn=db_conn,
            brain_id="stat_freq_global",
            name="Stat - Frequência Global",
            category="estatistico",
            version="v2",
        )

        self.freq = Counter({i: 0 for i in UNIVERSO})
        self.total_resultados = 0

        # carrega estado persistido (se existir)
        self.load_state()

    # ==================================================
    # CONTEXTO
    # ==================================================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # se ainda não há histórico no estado, relevância moderada
        return 1.0 if self.total_resultados > 0 else 0.6

    # ==================================================
    # GERAÇÃO
    # ==================================================
    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)

        # pesos com suavização para nunca zerar
        # (freq + 1) evita peso zero e mantém exploração
        weights: Dict[int, float] = {d: float(self.freq.get(d, 0) + 1) for d in UNIVERSO}

        # "core" mais frequentes (controla vício, mas ainda explora)
        # 15 -> core 18 / 18 -> core 22
        core_size = 18 if size == 15 else 22
        ranked = sorted(UNIVERSO, key=lambda d: weights[d], reverse=True)
        core = ranked[:core_size]

        jogos: List[List[int]] = []
        for _ in range(n):
            # mistura: parte do core e parte do universo
            # 15: ~70% core, 18: ~65% core
            frac_core = 0.70 if size == 15 else 0.65
            k_core = max(0, min(size, int(round(size * frac_core))))

            jogo = set()

            # 1) pega do core, ponderado pela frequência global
            if k_core > 0:
                w_core = {d: weights[d] for d in core}
                pick_core = weighted_sample_without_replacement(w_core, k_core)
                jogo.update(pick_core)

            # 2) completa com exploração no universo todo
            faltam = size - len(jogo)
            if faltam > 0:
                # exploração: favorece ainda as frequentes, mas permite todo o universo
                # vamos “achatar” pesos para não viciar demais
                w_uni = {d: (weights[d] ** 0.70) for d in UNIVERSO if d not in jogo}
                pick_uni = weighted_sample_without_replacement(w_uni, faltam)
                jogo.update(pick_uni)

            jogos.append(sorted(jogo))

        return jogos

    # ==================================================
    # SCORE INTERNO
    # ==================================================
    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        maxf = max(self.freq.values()) if self.freq else 1
        if maxf <= 0:
            return 0.0

        # score normalizado 0..1 (aprox)
        s = 0.0
        for d in jogo:
            s += float(self.freq.get(int(d), 0)) / float(maxf)
        return s / float(len(jogo))

    # ==================================================
    # APRENDIZADO (N -> N+1)
    # ==================================================
    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        """
        Aprendizado incremental:
        - Atualiza frequência global com o RESULTADO REAL (N+1)
        - Reforço leve para dezenas do 'jogo' quando foi muito bem (14/15)
        """
        if resultado_n1:
            # frequência global é baseada no resultado real
            for d in resultado_n1:
                self.freq[int(d)] += 1
            self.total_resultados += 1

        # reforço leve (não pode dominar a estatística global)
        # 14: +0.25 por dezena do jogo, 15: +0.50
        if pontos >= 14 and jogo:
            bonus = 0.50 if pontos >= 15 else 0.25
            for d in jogo:
                self.freq[int(d)] += bonus

        # salva no state (persistência via BaseBrain)
        self.state = {
            "freq": {str(k): float(v) for k, v in self.freq.items()},
            "total_resultados": int(self.total_resultados),
        }

        # performance por concurso (auditoria)
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==================================================
    # PERSISTÊNCIA
    # ==================================================
    def load_state(self) -> None:
        super().load_state()

        raw = self.state or {}
        freq_raw = raw.get("freq") or {}
        self.freq = Counter({i: 0 for i in UNIVERSO})

        # pode ter float por causa dos bônus
        for k, v in freq_raw.items():
            try:
                self.freq[int(k)] = float(v)
            except Exception:
                continue

        try:
            self.total_resultados = int(raw.get("total_resultados", 0))
        except Exception:
            self.total_resultados = 0

    # BaseBrain.save_state já existe e salva self.state no banco

    # ==================================================
    # RELATÓRIO
    # ==================================================
    def report(self) -> Dict[str, Any]:
        ranked = sorted(UNIVERSO, key=lambda d: self.freq.get(d, 0), reverse=True)
        return {
            **super().report(),
            "total_resultados": int(self.total_resultados),
            "top10": ranked[:10],
            "bottom10": ranked[-10:],
        }
