# training/brains/statistical/paridade_faixas_brain.py
from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Tuple

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, count_even


FAIXAS = [
    (1, 5),
    (6, 10),
    (11, 15),
    (16, 20),
    (21, 25),
]


def faixa_of(d: int) -> int:
    for i, (a, b) in enumerate(FAIXAS):
        if a <= d <= b:
            return i
    return -1


class StatParidadeFaixasBrain(BaseBrain):
    """
    Cérebro Estatístico: Paridade + Faixas Numéricas
    ------------------------------------------------
    Aprende distribuições reais observadas em jogos fortes (>=11)
    com reforço especial para 14/15.

    O que ele aprende:
    - nº de pares típico (ex: 7, 8, 9)
    - distribuição por faixas (ex: [3,3,3,3,3])

    O que ele faz:
    - gera jogos que respeitam essas distribuições
    - corrige excesso de concentração numa faixa
    """

    def __init__(self, db_conn, version: str = "v1"):
        super().__init__(
            db_conn=db_conn,
            brain_id="stat_paridade_faixas",
            name="Stat - Paridade e Faixas",
            category="estatistico",
            version=version,
        )

        self.dist_even: Counter[int] = Counter()
        self.dist_faixas: Counter[Tuple[int, ...]] = Counter()
        self.learn_steps = 0

        self.load_state()

    # ==========================
    # BrainInterface
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # sempre relevante como refinador
        return 0.85

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        jogos: List[List[int]] = []

        if not self.dist_even or not self.dist_faixas:
            # fallback: gera aleatório balanceado
            for _ in range(n):
                jogos.append(sorted(random.sample(UNIVERSO, size)))
            return jogos

        alvo_even = self._sample_even()
        alvo_faixas = self._sample_faixas()

        for _ in range(n):
            jogo = set()

            # tenta preencher por faixas
            for idx, qtd in enumerate(alvo_faixas):
                pool = [d for d in UNIVERSO if faixa_of(d) == idx and d not in jogo]
                if pool:
                    jogo.update(random.sample(pool, min(qtd, len(pool))))

            # completa se faltar
            while len(jogo) < size:
                jogo.add(random.choice(UNIVERSO))

            jogo = sorted(jogo)

            # micro-ajuste de paridade
            for _ in range(8):
                ev = count_even(jogo)
                if abs(ev - alvo_even) <= 1:
                    break

                if ev > alvo_even:
                    # remove par
                    pares = [d for d in jogo if d % 2 == 0]
                    if pares:
                        jogo.remove(random.choice(pares))
                else:
                    # remove ímpar
                    imp = [d for d in jogo if d % 2 == 1]
                    if imp:
                        jogo.remove(random.choice(imp))

                # adiciona oposto
                pool = [d for d in UNIVERSO if d not in jogo]
                if pool:
                    jogo.append(random.choice(pool))
                jogo = sorted(set(jogo))

            jogos.append(sorted(jogo[:size]))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        ev = count_even(jogo)
        fa = [0] * 5
        for d in jogo:
            fa[faixa_of(d)] += 1

        # score baseado na proximidade das distribuições aprendidas
        s_even = self.dist_even.get(ev, 0)
        s_faixa = self.dist_faixas.get(tuple(fa), 0)

        return float(0.6 * s_even + 0.4 * s_faixa)

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        self.learn_steps += 1

        if pontos < 11:
            return

        peso = 3 if pontos >= 14 else 1

        ev = count_even(jogo)
        fa = [0] * 5
        for d in jogo:
            fa[faixa_of(d)] += 1

        self.dist_even[ev] += peso
        self.dist_faixas[tuple(fa)] += peso

        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # Persistência
    # ==========================
    def save_state(self) -> None:
        self.state = {
            "learn_steps": self.learn_steps,
            "dist_even": dict(self.dist_even),
            "dist_faixas": {",".join(map(str, k)): v for k, v in self.dist_faixas.items()},
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()
        try:
            self.learn_steps = int(self.state.get("learn_steps", 0))
            self.dist_even = Counter({int(k): int(v) for k, v in self.state.get("dist_even", {}).items()})
            self.dist_faixas = Counter({
                tuple(map(int, k.split(","))): int(v)
                for k, v in self.state.get("dist_faixas", {}).items()
            })
        except Exception:
            self.dist_even = Counter()
            self.dist_faixas = Counter()

    # ==========================
    # Internos
    # ==========================
    def _sample_even(self) -> int:
        total = sum(self.dist_even.values())
        r = random.uniform(0, total)
        acc = 0
        for k, v in self.dist_even.items():
            acc += v
            if acc >= r:
                return int(k)
        return random.choice(list(self.dist_even.keys()))

    def _sample_faixas(self) -> List[int]:
        total = sum(self.dist_faixas.values())
        r = random.uniform(0, total)
        acc = 0
        for k, v in self.dist_faixas.items():
            acc += v
            if acc >= r:
                return list(k)
        return list(random.choice(list(self.dist_faixas.keys())))
