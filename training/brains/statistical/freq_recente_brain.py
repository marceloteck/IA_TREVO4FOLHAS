from __future__ import annotations

from collections import Counter, deque
from typing import Any, Dict, List, Optional
import random

from training.core.brain_interface import BrainInterface


class StatFreqRecenteBrain(BrainInterface):
    id = "stat_freq_recente"
    name = "Stat - Frequência Recente"
    category = "estatistico"
    version = "v1"

    def __init__(self, db, janela: int = 120):
        super().__init__(db)
        self.janela = int(janela)
        self.buffer = deque(maxlen=self.janela)  # cada item = resultado_n1
        self.freq = Counter()

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # se a janela está vazia, relevância menor
        return 0.6 if not self.buffer else 1.0

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        if not resultado_n1:
            return

        # remove o que sair do buffer
        if len(self.buffer) == self.buffer.maxlen:
            old = self.buffer[0]
            self.freq.subtract(old)
            # limpa contagens negativas (Counter pode ficar com negativos)
            for k in list(self.freq.keys()):
                if self.freq[k] <= 0:
                    del self.freq[k]

        novo = [int(x) for x in resultado_n1]
        self.buffer.append(novo)
        self.freq.update(novo)

    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        tamanho = int(context.get("tamanho", 15))
        n = int(context.get("n", 60))

        universo = list(range(1, 26))
        ranked = sorted(universo, key=lambda d: self.freq[d], reverse=True)

        # recência costuma “mover” mais — então exploramos um pouco mais
        core_size = 16 if tamanho == 15 else 20
        core = ranked[:core_size]

        jogos = []
        for _ in range(n):
            jogo = set()

            k_core = max(0, min(len(core), int(tamanho * 0.60)))
            pool_core = core[:]
            weights_core = [float(self.freq[d] + 1) for d in pool_core]
            # amostragem simples (sem repetição)
            while len(jogo) < k_core and pool_core:
                d = random.choices(pool_core, weights=weights_core, k=1)[0]
                idx = pool_core.index(d)
                pool_core.pop(idx)
                weights_core.pop(idx)
                jogo.add(d)

            # completa com universo
            while len(jogo) < tamanho:
                jogo.add(random.choice(universo))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        maxf = max(self.freq.values()) if self.freq else 1
        return sum((self.freq[int(d)] / maxf) for d in jogo) / len(jogo)

    def save_state(self) -> Dict[str, Any]:
        return {
            "janela": int(self.janela),
            "buffer": [list(map(int, x)) for x in self.buffer],
        }

    def load_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        if not state:
            return
        self.janela = int(state.get("janela", self.janela))
        buff = state.get("buffer", []) or []
        self.buffer = deque([list(map(int, x)) for x in buff], maxlen=self.janela)
        self.freq = Counter()
        for arr in self.buffer:
            self.freq.update(arr)
