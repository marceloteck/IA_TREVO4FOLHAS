# src/training/core/brain.py

from collections import Counter, defaultdict
from typing import List, Dict, Tuple
import random


class Brain:
    """
    Cérebro central de aprendizado incremental N -> N+1
    """

    def __init__(self, db):
        self.db = db

        # ===============================
        # 🧠 MEMÓRIAS INTERNAS
        # ===============================
        self.freq_global = Counter()
        self.freq_recente = Counter()

        self.pares = Counter()
        self.trios = Counter()

        self.pesos_dezenas = defaultdict(float)
        self.pesos_pares = defaultdict(float)
        self.pesos_padroes = defaultdict(float)

        self.historico_contextos = []

    # ===============================
    # 🎯 GERAÇÃO DE JOGO
    # ===============================
    def gerar_jogo(self, tamanho: int = 15) -> List[int]:
        """
        Geração guiada por pesos e padrões
        """
        universo = list(range(1, 26))

        # Score de cada dezena
        scores = []
        for d in universo:
            score = (
                self.freq_global[d] * 0.3 +
                self.freq_recente[d] * 0.5 +
                self.pesos_dezenas[d]
            )
            scores.append((d, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        # Mistura exploração + exploração
        base = [d for d, _ in scores[:18]]
        jogo = sorted(random.sample(base, tamanho))

        return jogo

    # ===============================
    # 🧪 AVALIAÇÃO
    # ===============================
    def avaliar_jogo(self, jogo: List[int], resultado_real: List[int]) -> int:
        return len(set(jogo) & set(resultado_real))

    # ===============================
    # 🎓 APRENDIZADO
    # ===============================
    def aprender(
        self,
        concurso: int,
        jogo: List[int],
        pontos: int,
        resultado_real: List[int]
    ):
        # Frequência básica
        for d in jogo:
            self.freq_global[d] += 1

        # Pares
        for i in range(len(jogo)):
            for j in range(i + 1, len(jogo)):
                self.pares[(jogo[i], jogo[j])] += 1

        # Reforço / penalização
        self._ajustar_pesos(jogo, pontos)

        # Memória temporal
        self.historico_contextos.append({
            "concurso": concurso,
            "jogo": jogo,
            "resultado": resultado_real,
            "pontos": pontos
        })

    # ===============================
    # ⚖️ AJUSTE DE PESOS
    # ===============================
    def _ajustar_pesos(self, jogo: List[int], pontos: int):
        if pontos >= 14:
            fator = 2.5
        elif pontos >= 13:
            fator = 1.5
        elif pontos >= 11:
            fator = 0.7
        else:
            fator = -0.3

        for d in jogo:
            self.pesos_dezenas[d] += fator

    # ===============================
    # 🔥 CONSOLIDAÇÃO
    # ===============================
    def consolidar(self):
        """
        Chamado ao final do treinamento
        """
        # Normalizações futuras
        pass

    # ===============================
    # 🎯 GERAÇÃO FINAL
    # ===============================
    def gerar_jogos_finais(self, qtd_15=10, qtd_18=7):
        jogos_15 = [self.gerar_jogo(15) for _ in range(qtd_15)]
        jogos_18 = [self.gerar_jogo(18) for _ in range(qtd_18)]
        return jogos_15, jogos_18
