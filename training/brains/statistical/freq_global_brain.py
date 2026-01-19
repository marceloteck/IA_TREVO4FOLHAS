from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional
import random

from training.core.brain_interface import BrainInterface


def _weighted_choice_no_replace(pool: List[int], weights: List[float], k: int) -> List[int]:
    k = max(0, min(k, len(pool)))
    escolhidos = []
    for _ in range(k):
        total = sum(weights)
        if total <= 0:
            idx = random.randrange(len(pool))
        else:
            r = random.random() * total
            acc = 0.0
            idx = 0
            for i, w in enumerate(weights):
                acc += w
                if acc >= r:
                    idx = i
                    break
        escolhidos.append(pool.pop(idx))
        weights.pop(idx)
    return escolhidos


class StatFreqGlobalBrain(BrainInterface):
    id = "stat_freq_global"
    name = "Stat - Frequência Global"
    category = "estatistico"
    version = "v1"

    def __init__(self, db):
        super().__init__(db)
        self.freq = Counter()
        self.draws = 0

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        return 1.0

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        if resultado_n1:
            self.freq.update([int(x) for x in resultado_n1])
            self.draws += 1

    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        tamanho = int(context.get("tamanho", 15))
        n = int(context.get("n", 60))

        universo = list(range(1, 26))
        ranked = sorted(universo, key=lambda d: self.freq[d], reverse=True)

        # Core forte (quanto maior o tamanho, maior o core)
        core_size = 18 if tamanho == 15 else 22
        core = ranked[:core_size]

        jogos: List[List[int]] = []

        for _ in range(n):
            jogo = set()

            # 70% core + 30% universo (exploração controlada)
            k_core = max(0, min(len(core), int(tamanho * 0.70)))
            pool = core[:]
            weights = [float(self.freq[d] + 1) for d in pool]
            jogo.update(_weighted_choice_no_replace(pool, weights, k_core))

            rest = tamanho - len(jogo)
            if rest > 0:
                pool2 = [d for d in universo if d not in jogo]
                weights2 = [float(self.freq[d] + 1) for d in pool2]
                jogo.update(_weighted_choice_no_replace(pool2, weights2, rest))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        maxf = max(self.freq.values()) if self.freq else 1
        return sum((self.freq[int(d)] / maxf) for d in jogo) / len(jogo)

    def save_state(self) -> Dict[str, Any]:
        return {
            "draws": int(self.draws),
            "freq": {str(k): int(v) for k, v in self.freq.items()},
        }

    def load_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        if not state:
            return
        self.draws = int(state.get("draws", 0))
        freq = state.get("freq", {}) or {}
        self.freq = Counter({int(k): int(v) for k, v in freq.items()})

