from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple
import random

from training.core.brain_interface import BrainInterface


class StatParesBrain(BrainInterface):
    id = "stat_pares"
    name = "Stat - Pares & Co-ocorrência"
    category = "estatistico"
    version = "v1"

    def __init__(self, db):
        super().__init__(db)
        self.pares = Counter()  # (a,b) ordenado
        self.freq = Counter()   # apoio

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # quanto mais pares aprendidos, maior relevância
        return 0.5 if not self.pares else 1.0

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        if not resultado_n1:
            return
        dezenas = sorted(set(int(x) for x in resultado_n1))
        self.freq.update(dezenas)
        for i in range(len(dezenas)):
            for j in range(i + 1, len(dezenas)):
                self.pares[(dezenas[i], dezenas[j])] += 1

    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        tamanho = int(context.get("tamanho", 15))
        n = int(context.get("n", 60))
        universo = list(range(1, 26))

        jogos = []
        top_nums = [d for d, _ in self.freq.most_common(18)] or universo[:]

        for _ in range(n):
            jogo = set()

            # começa com um número forte
            base = random.choice(top_nums)
            jogo.add(base)

            # expande por pares mais fortes com o que já existe
            while len(jogo) < tamanho:
                candidatos = []
                for x in list(jogo):
                    for y in universo:
                        if y in jogo:
                            continue
                        a, b = (x, y) if x < y else (y, x)
                        score = self.pares.get((a, b), 0)
                        candidatos.append((y, score))

                candidatos.sort(key=lambda t: t[1], reverse=True)

                # 80% pega do topo por pares, 20% aleatório
                if candidatos and random.random() < 0.80:
                    top = candidatos[:8]
                    y = random.choice([t[0] for t in top])
                    jogo.add(y)
                else:
                    jogo.add(random.choice(universo))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        dezenas = sorted(set(int(x) for x in jogo))
        s = 0.0
        for i in range(len(dezenas)):
            for j in range(i + 1, len(dezenas)):
                s += float(self.pares.get((dezenas[i], dezenas[j]), 0))
        return s / 200.0  # normalização leve (comparativo)

    def save_state(self) -> Dict[str, Any]:
        return {
            "freq": {str(k): int(v) for k, v in self.freq.items()},
            "pares": {f"{a}-{b}": int(v) for (a, b), v in self.pares.items()},
        }

    def load_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        if not state:
            return
        self.freq = Counter({int(k): int(v) for k, v in (state.get("freq") or {}).items()})
        pares_raw = state.get("pares") or {}
        self.pares = Counter()
        for k, v in pares_raw.items():
            a, b = k.split("-")
            self.pares[(int(a), int(b))] = int(v)
