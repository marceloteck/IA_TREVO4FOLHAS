# training/brains/structural/pattern_shape_brain.py
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple
import random

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, count_even, max_consecutive_run, weighted_sample_without_replacement


def _bucket_sum(total: int) -> str:
    # Buckets bem simples (ajustável depois sem quebrar compatibilidade)
    if total < 170:
        return "sum_lt_170"
    if total < 190:
        return "sum_170_189"
    if total < 210:
        return "sum_190_209"
    if total < 230:
        return "sum_210_229"
    return "sum_ge_230"


def _band_counts(jogo: List[int]) -> Tuple[int, int, int, int, int]:
    # 1-5, 6-10, 11-15, 16-20, 21-25
    b1 = sum(1 for x in jogo if 1 <= x <= 5)
    b2 = sum(1 for x in jogo if 6 <= x <= 10)
    b3 = sum(1 for x in jogo if 11 <= x <= 15)
    b4 = sum(1 for x in jogo if 16 <= x <= 20)
    b5 = sum(1 for x in jogo if 21 <= x <= 25)
    return (b1, b2, b3, b4, b5)


def _shape_key(jogo: List[int]) -> str:
    jogo = sorted(int(x) for x in jogo)
    ev = count_even(jogo)
    run = max_consecutive_run(jogo)
    bands = _band_counts(jogo)
    s = sum(jogo)
    return f"e{ev}_r{run}_b{bands[0]}{bands[1]}{bands[2]}{bands[3]}{bands[4]}_{_bucket_sum(s)}"


class StructuralPatternShapeBrain(BaseBrain):
    """
    Cérebro Estrutural: aprende "shape" (forma) de jogos bons.
    - NÃO tenta prever dezenas específicas.
    - Aprende quais formatos aparecem mais quando o acerto é alto.
    - Gera jogos respeitando shapes prováveis, misturando exploração.
    """

    def __init__(self, db_conn, version: str = "v1"):
        super().__init__(
            db_conn=db_conn,
            brain_id="struct_shape",
            name="Structural - Pattern Shape",
            category="estrutural",
            version=version,
        )

        # contadores por shape, separados por faixa de pontos
        self.shape_11 = Counter()
        self.shape_13 = Counter()
        self.shape_14 = Counter()

        self.total_learns = 0

        self.load_state()
        self._rebuild_from_state()

    # --------------------------
    # BrainInterface
    # --------------------------
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # se ainda não aprendeu nada, relevância menor (mas não zero)
        learned = self.total_learns
        if learned <= 0:
            return 0.35
        if learned < 200:
            return 0.55
        return 0.75

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18):
            size = 15

        # escolhe de qual “memória de shape” puxar
        # 15 dezenas: foca mais em 14+; 18: foca em 13+ (mais permissivo)
        if size == 15 and self.shape_14:
            source = self.shape_14
        elif self.shape_13:
            source = self.shape_13
        else:
            source = self.shape_11

        # se ainda vazio, gera aleatório com leve controle
        jogos: List[List[int]] = []
        if not source:
            for _ in range(n):
                jogos.append(sorted(random.sample(UNIVERSO, size)))
            return jogos

        # amostra shapes por peso
        keys = list(source.keys())
        weights = [max(1.0, float(source[k])) for k in keys]

        for _ in range(n):
            target = random.choices(keys, weights=weights, k=1)[0]
            jogo = self._generate_with_shape(target, size=size)
            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        # score: quanto esse jogo “bate” com shapes premiados
        if not jogo:
            return 0.0
        k = _shape_key(jogo)

        s14 = float(self.shape_14.get(k, 0))
        s13 = float(self.shape_13.get(k, 0))
        s11 = float(self.shape_11.get(k, 0))

        # normalização simples (comparativo)
        denom = 1.0 + s11 + 1.5 * s13 + 2.5 * s14
        return (s11 + 1.5 * s13 + 2.5 * s14) / denom

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        # aprende baseado no jogo que foi avaliado (candidato) + pontos obtidos no resultado real N+1
        if not jogo:
            return

        key = _shape_key(jogo)

        if pontos >= 14:
            self.shape_14[key] += 1
            self.shape_13[key] += 1
            self.shape_11[key] += 1
        elif pontos >= 13:
            self.shape_13[key] += 1
            self.shape_11[key] += 1
        elif pontos >= 11:
            self.shape_11[key] += 1

        self.total_learns += 1

        # performance por concurso (leve)
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

        # autosave leve (micro-melhoria): salva a cada X learns
        # (o Hub também salva periodicamente, mas isso protege contra crash)
        if self.total_learns % 250 == 0:
            self.save_state()

    # --------------------------
    # Persistência
    # --------------------------
    def save_state(self) -> None:
        self.state = {
            "total_learns": int(self.total_learns),
            "shape_11": dict(self.shape_11),
            "shape_13": dict(self.shape_13),
            "shape_14": dict(self.shape_14),
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

    def _rebuild_from_state(self) -> None:
        try:
            self.total_learns = int(self.state.get("total_learns", 0))
            self.shape_11 = Counter(self.state.get("shape_11", {}) or {})
            self.shape_13 = Counter(self.state.get("shape_13", {}) or {})
            self.shape_14 = Counter(self.state.get("shape_14", {}) or {})
        except Exception:
            self.total_learns = 0
            self.shape_11 = Counter()
            self.shape_13 = Counter()
            self.shape_14 = Counter()

    def report(self) -> Dict[str, Any]:
        top14 = [k for k, _ in self.shape_14.most_common(5)]
        return {
            **super().report(),
            "total_learns": int(self.total_learns),
            "unique_shapes_11": len(self.shape_11),
            "unique_shapes_13": len(self.shape_13),
            "unique_shapes_14": len(self.shape_14),
            "top_shapes_14": top14,
        }

    # --------------------------
    # Geração por shape
    # --------------------------
    def _generate_with_shape(self, key: str, size: int) -> List[int]:
        """
        Interpreta o shape key e tenta montar um jogo que respeita:
        - evens
        - max_run
        - band counts
        - sum bucket (aproximado)
        """
        # parse simples
        # formato: e{ev}_r{run}_b{b1}{b2}{b3}{b4}{b5}_{sum_bucket}
        parts = key.split("_")
        ev = int(parts[0][1:]) if parts and parts[0].startswith("e") else 7
        run = int(parts[1][1:]) if len(parts) > 1 and parts[1].startswith("r") else 3

        band = (3, 3, 3, 3, 3)  # default
        if len(parts) > 2 and parts[2].startswith("b"):
            b = parts[2][1:]
            if len(b) == 5 and all(ch.isdigit() for ch in b):
                band = (int(b[0]), int(b[1]), int(b[2]), int(b[3]), int(b[4]))

        # pools por faixa
        pools = [
            [x for x in UNIVERSO if 1 <= x <= 5],
            [x for x in UNIVERSO if 6 <= x <= 10],
            [x for x in UNIVERSO if 11 <= x <= 15],
            [x for x in UNIVERSO if 16 <= x <= 20],
            [x for x in UNIVERSO if 21 <= x <= 25],
        ]

        jogo: List[int] = []

        # 1) respeita distribuição por faixas (se passar do tamanho, ajusta)
        target = list(band)
        if sum(target) != size:
            # ajusta proporcionalmente: mantém a “cara” mas encaixa no tamanho
            s = sum(target) if sum(target) > 0 else 1
            scaled = [max(0, int(round(size * (t / s)))) for t in target]
            # corrige diferença
            while sum(scaled) < size:
                scaled[scaled.index(max(scaled))] += 1
            while sum(scaled) > size:
                i = scaled.index(max(scaled))
                if scaled[i] > 0:
                    scaled[i] -= 1
                else:
                    break
            target = scaled

        for pool, k in zip(pools, target):
            if k <= 0:
                continue
            picks = random.sample(pool, min(k, len(pool)))
            jogo.extend(picks)

        # 2) se ainda faltou (por falta no pool), completa
        jogo = list(dict.fromkeys(jogo))  # remove duplicatas mantendo ordem
        while len(jogo) < size:
            x = random.choice(UNIVERSO)
            if x not in jogo:
                jogo.append(x)

        # 3) ajusta paridade (aproximado) via swaps
        jogo = sorted(jogo)
        for _ in range(20):
            cur_even = count_even(jogo)
            if cur_even == ev:
                break
            if cur_even < ev:
                # trocar um ímpar por par
                odds = [x for x in jogo if x % 2 == 1]
                evens_pool = [x for x in UNIVERSO if x % 2 == 0 and x not in jogo]
                if not odds or not evens_pool:
                    break
                jogo.remove(random.choice(odds))
                jogo.append(random.choice(evens_pool))
            else:
                # trocar um par por ímpar
                evens = [x for x in jogo if x % 2 == 0]
                odds_pool = [x for x in UNIVERSO if x % 2 == 1 and x not in jogo]
                if not evens or not odds_pool:
                    break
                jogo.remove(random.choice(evens))
                jogo.append(random.choice(odds_pool))
            jogo = sorted(jogo)

        # 4) evita sequência muito grande (run) com pequenos swaps
        for _ in range(25):
            if max_consecutive_run(jogo) <= run:
                break
            # remove um número do meio de uma sequência e substitui por outro distante
            candidates_remove = jogo[:]
            random.shuffle(candidates_remove)
            removed = None
            for r in candidates_remove:
                temp = [x for x in jogo if x != r]
                if max_consecutive_run(temp) < max_consecutive_run(jogo):
                    removed = r
                    jogo = temp
                    break
            if removed is None:
                break
            # adiciona um número fora do jogo e que não crie sequência grande
            pool = [x for x in UNIVERSO if x not in jogo]
            random.shuffle(pool)
            for x in pool:
                temp = sorted(jogo + [x])
                if max_consecutive_run(temp) <= run:
                    jogo = temp
                    break
            # garante tamanho
            while len(jogo) < size:
                x = random.choice([u for u in UNIVERSO if u not in jogo])
                jogo.append(x)
                jogo = sorted(jogo)

        return sorted(jogo)
