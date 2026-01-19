from __future__ import annotations

from typing import Any, Dict, List, Optional
import random

from training.core.brain_interface import BrainInterface


class TemporalAtrasoBrain(BrainInterface):
    id = "temporal_atraso"
    name = "Temporal - Atraso (atualização controlada)"
    category = "temporal"
    version = "v1"

    def __init__(self, db):
        super().__init__(db)
        self.ultimo_concurso_visto = 0
        self.last_seen = {i: 0 for i in range(1, 26)}  # concurso onde apareceu por último

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # útil quando você quer diversidade e evitar “vício”
        return 0.85

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        # atualiza com o concurso N+1 (resultado real)
        concurso_n1 = int(concurso_n) + 1
        for d in resultado_n1 or []:
            self.last_seen[int(d)] = concurso_n1
        self.ultimo_concurso_visto = max(self.ultimo_concurso_visto, concurso_n1)

    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        tamanho = int(context.get("tamanho", 15))
        n = int(context.get("n", 60))

        concurso_n = int(context.get("concurso_n", self.ultimo_concurso_visto))
        universo = list(range(1, 26))

        # atraso = quanto tempo não aparece
        atrasos = [(d, concurso_n - self.last_seen.get(d, 0)) for d in universo]
        atrasos.sort(key=lambda x: x[1], reverse=True)

        # pega um core de “mais atrasadas”, mas mistura com universo
        core = [d for d, _ in atrasos[:16]]

        jogos = []
        for _ in range(n):
            jogo = set()

            # 50% core de atraso
            while len(jogo) < int(tamanho * 0.50):
                jogo.add(random.choice(core))

            # completa com diversidade
            while len(jogo) < tamanho:
                jogo.add(random.choice(universo))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        concurso_n = int(context.get("concurso_n", self.ultimo_concurso_visto))
        if not jogo:
            return 0.0
        s = 0.0
        for d in jogo:
            s += float(concurso_n - self.last_seen.get(int(d), 0))
        return s / 100.0  # comparativo

    def save_state(self) -> Dict[str, Any]:
        return {
            "ultimo_concurso_visto": int(self.ultimo_concurso_visto),
            "last_seen": {str(k): int(v) for k, v in self.last_seen.items()},
        }

    def load_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        if not state:
            return
        self.ultimo_concurso_visto = int(state.get("ultimo_concurso_visto", 0))
        raw = state.get("last_seen") or {}
        self.last_seen = {int(k): int(v) for k, v in raw.items()}
