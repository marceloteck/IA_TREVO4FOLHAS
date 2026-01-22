from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from training.brains._utils import UNIVERSO, max_consecutive_run, weighted_sample_without_replacement
from training.core.base_brain import BaseBrain

PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23}
FIBONACCI = {1, 2, 3, 5, 8, 13, 21}
MULTIPLOS_3 = {3, 6, 9, 12, 15, 18, 21, 24}
MOLDURA = {
    1, 2, 3, 4, 5,
    6, 10,
    11, 15,
    16, 20,
    21, 22, 23, 24, 25,
}


@dataclass(frozen=True)
class HeuristicConfig:
    brain_id: str
    name: str
    category: str
    version: str
    constraints: Dict[str, Any]
    recent_bias: float = 0.65
    max_attempts: int = 200


class HeuristicPatternBrain(BaseBrain):
    """
    Cérebro heurístico parametrizável.
    Usa constraints simples (paridade, soma, distribuição, primos, sequências, linhas/colunas)
    com geração baseada em amostragem ponderada por frequência recente.
    """

    def __init__(self, db_conn, config: HeuristicConfig):
        super().__init__(
            db_conn=db_conn,
            brain_id=config.brain_id,
            name=config.name,
            category=config.category,
            version=config.version,
        )
        self.config = config
        self.state = self.state or {"jogos": 0, "q14": 0, "q15": 0}

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        historico = context.get("historico_recente") or []
        base = 0.55
        if len(historico) >= 30:
            base += 0.1
        if len(historico) >= 120:
            base += 0.1
        return min(0.95, base)

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        jogos: List[List[int]] = []
        attempts = 0
        max_attempts = max(10, n * int(self.config.max_attempts))

        while len(jogos) < n and attempts < max_attempts:
            jogo = self._sample_game(size=size, context=context)
            attempts += 1
            if self._passes_constraints(jogo, size, context):
                jogos.append(sorted(jogo))

        while len(jogos) < n:
            jogos.append(sorted(self._sample_game(size=size, context=context)))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0

        constraints = self.config.constraints
        size = len(jogo)
        scores = []

        odd_target = self._scaled_value(constraints.get("odd_target"), size)
        odd_tol = constraints.get("odd_tol", 1)
        if odd_target is not None:
            odd_count = sum(1 for x in jogo if x % 2 != 0)
            scores.append(self._target_score(odd_count, odd_target, odd_tol))

        even_target = self._scaled_value(constraints.get("even_target"), size)
        even_tol = constraints.get("even_tol", 1)
        if even_target is not None:
            even_count = sum(1 for x in jogo if x % 2 == 0)
            scores.append(self._target_score(even_count, even_target, even_tol))

        low_target = self._scaled_value(constraints.get("low_target"), size)
        low_tol = constraints.get("low_tol", 1)
        if low_target is not None:
            low_count = sum(1 for x in jogo if x <= 12)
            scores.append(self._target_score(low_count, low_target, low_tol))

        prime_target = self._scaled_value(constraints.get("prime_target"), size)
        prime_tol = constraints.get("prime_tol", 1)
        if prime_target is not None:
            prime_count = sum(1 for x in jogo if x in PRIMES)
            scores.append(self._target_score(prime_count, prime_target, prime_tol))

        mult3_target = self._scaled_value(constraints.get("mult3_target"), size)
        mult3_tol = constraints.get("mult3_tol", 1)
        if mult3_target is not None:
            mult3_count = sum(1 for x in jogo if x in MULTIPLOS_3)
            scores.append(self._target_score(mult3_count, mult3_target, mult3_tol))

        fib_target = self._scaled_value(constraints.get("fib_target"), size)
        fib_tol = constraints.get("fib_tol", 1)
        if fib_target is not None:
            fib_count = sum(1 for x in jogo if x in FIBONACCI)
            scores.append(self._target_score(fib_count, fib_target, fib_tol))

        moldura_target = self._scaled_value(constraints.get("moldura_target"), size)
        moldura_tol = constraints.get("moldura_tol", 1)
        if moldura_target is not None:
            moldura_count = sum(1 for x in jogo if x in MOLDURA)
            scores.append(self._target_score(moldura_count, moldura_target, moldura_tol))

        repeat_target = self._scaled_value(constraints.get("repeat_target"), size)
        repeat_tol = constraints.get("repeat_tol", 1)
        if repeat_target is not None:
            ultimo = context.get("ultimo_resultado") or []
            repeat_count = len(set(jogo) & set(ultimo))
            scores.append(self._target_score(repeat_count, repeat_target, repeat_tol))

        max_run = constraints.get("max_run")
        if max_run is not None:
            run = max_consecutive_run(jogo)
            scores.append(self._cap_score(run, max_run))

        sum_range = self._scaled_sum_range(constraints.get("sum_range"), size)
        if sum_range is not None:
            min_sum, max_sum = sum_range
            total = sum(jogo)
            scores.append(self._range_score(total, min_sum, max_sum))

        row_cap = self._scaled_value(constraints.get("row_cap"), size)
        if row_cap is not None:
            row_counts, col_counts = self._row_col_counts(jogo)
            scores.append(self._cap_score(max(row_counts), row_cap))

        col_cap = self._scaled_value(constraints.get("col_cap"), size)
        if col_cap is not None:
            row_counts, col_counts = self._row_col_counts(jogo)
            scores.append(self._cap_score(max(col_counts), col_cap))

        freq_score = self._freq_score(jogo, context)
        scores.append(freq_score)

        return sum(scores) / float(len(scores))

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        self.state["jogos"] = int(self.state.get("jogos", 0)) + 1
        if pontos >= 14:
            self.state["q14"] = int(self.state.get("q14", 0)) + 1
        if pontos >= 15:
            self.state["q15"] = int(self.state.get("q15", 0)) + 1

        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    def _sample_game(self, size: int, context: Dict[str, Any]) -> List[int]:
        freq = context.get("freq_recente") or {}
        constraints = self.config.constraints
        fixed_numbers = [int(x) for x in constraints.get("fixed_numbers", []) if 1 <= int(x) <= 25]
        excluded_numbers = {int(x) for x in constraints.get("excluded_numbers", []) if 1 <= int(x) <= 25}
        weights = {}
        for d in UNIVERSO:
            if d in excluded_numbers:
                continue
            base = float(freq.get(d, 0)) + 1.0
            weights[d] = base ** (0.75 + 0.5 * self.config.recent_bias)
        jogo = set(fixed_numbers[: size])
        faltam = size - len(jogo)
        if faltam > 0:
            w_pool = {d: w for d, w in weights.items() if d not in jogo}
            if not w_pool:
                w_pool = {d: 1.0 for d in UNIVERSO if d not in jogo}
            jogo.update(weighted_sample_without_replacement(w_pool, faltam))
        return sorted(jogo)

    def _passes_constraints(self, jogo: List[int], size: int, context: Dict[str, Any]) -> bool:
        constraints = self.config.constraints

        odd_target = self._scaled_value(constraints.get("odd_target"), size)
        odd_tol = constraints.get("odd_tol", 1)
        if odd_target is not None:
            odd_count = sum(1 for x in jogo if x % 2 != 0)
            if abs(odd_count - odd_target) > odd_tol:
                return False

        even_target = self._scaled_value(constraints.get("even_target"), size)
        even_tol = constraints.get("even_tol", 1)
        if even_target is not None:
            even_count = sum(1 for x in jogo if x % 2 == 0)
            if abs(even_count - even_target) > even_tol:
                return False

        low_target = self._scaled_value(constraints.get("low_target"), size)
        low_tol = constraints.get("low_tol", 1)
        if low_target is not None:
            low_count = sum(1 for x in jogo if x <= 12)
            if abs(low_count - low_target) > low_tol:
                return False

        prime_target = self._scaled_value(constraints.get("prime_target"), size)
        prime_tol = constraints.get("prime_tol", 1)
        if prime_target is not None:
            prime_count = sum(1 for x in jogo if x in PRIMES)
            if abs(prime_count - prime_target) > prime_tol:
                return False

        mult3_target = self._scaled_value(constraints.get("mult3_target"), size)
        mult3_tol = constraints.get("mult3_tol", 1)
        if mult3_target is not None:
            mult3_count = sum(1 for x in jogo if x in MULTIPLOS_3)
            if abs(mult3_count - mult3_target) > mult3_tol:
                return False

        fib_target = self._scaled_value(constraints.get("fib_target"), size)
        fib_tol = constraints.get("fib_tol", 1)
        if fib_target is not None:
            fib_count = sum(1 for x in jogo if x in FIBONACCI)
            if abs(fib_count - fib_target) > fib_tol:
                return False

        moldura_target = self._scaled_value(constraints.get("moldura_target"), size)
        moldura_tol = constraints.get("moldura_tol", 1)
        if moldura_target is not None:
            moldura_count = sum(1 for x in jogo if x in MOLDURA)
            if abs(moldura_count - moldura_target) > moldura_tol:
                return False

        repeat_target = self._scaled_value(constraints.get("repeat_target"), size)
        repeat_tol = constraints.get("repeat_tol", 1)
        if repeat_target is not None:
            ultimo = context.get("ultimo_resultado") or []
            repeat_count = len(set(jogo) & set(ultimo))
            if abs(repeat_count - repeat_target) > repeat_tol:
                return False

        max_run = constraints.get("max_run")
        if max_run is not None and max_consecutive_run(jogo) > max_run:
            return False

        sum_range = self._scaled_sum_range(constraints.get("sum_range"), size)
        if sum_range is not None:
            min_sum, max_sum = sum_range
            total = sum(jogo)
            if not (min_sum <= total <= max_sum):
                return False

        row_cap = self._scaled_value(constraints.get("row_cap"), size)
        if row_cap is not None:
            row_counts, col_counts = self._row_col_counts(jogo)
            if max(row_counts) > row_cap:
                return False

        col_cap = self._scaled_value(constraints.get("col_cap"), size)
        if col_cap is not None:
            row_counts, col_counts = self._row_col_counts(jogo)
            if max(col_counts) > col_cap:
                return False

        return True

    def _scaled_value(self, base_value: Optional[int], size: int) -> Optional[int]:
        if base_value is None:
            return None
        return max(1, int(round(base_value * size / 15)))

    def _scaled_sum_range(self, base_range: Optional[Tuple[int, int]], size: int) -> Optional[Tuple[int, int]]:
        if base_range is None:
            return None
        min_sum, max_sum = base_range
        factor = size / 15.0
        return int(round(min_sum * factor)), int(round(max_sum * factor))

    def _freq_score(self, jogo: List[int], context: Dict[str, Any]) -> float:
        freq = context.get("freq_recente") or {}
        if not freq:
            return 0.5
        maxf = max(freq.values()) if freq else 1
        if maxf <= 0:
            return 0.5
        score = sum(float(freq.get(d, 0)) / float(maxf) for d in jogo) / float(len(jogo))
        return 0.2 + 0.8 * score

    def _target_score(self, value: int, target: int, tolerance: int) -> float:
        diff = abs(value - target)
        if tolerance <= 0:
            return 1.0 if diff == 0 else 0.0
        return max(0.0, 1.0 - (diff / float(tolerance + 1)))

    def _cap_score(self, value: int, cap: int) -> float:
        if value <= cap:
            return 1.0
        return max(0.0, 1.0 - (value - cap) / float(cap + 1))

    def _range_score(self, value: int, min_value: int, max_value: int) -> float:
        if min_value <= value <= max_value:
            return 1.0
        if value < min_value:
            return max(0.0, 1.0 - (min_value - value) / float(max_value - min_value + 1))
        return max(0.0, 1.0 - (value - max_value) / float(max_value - min_value + 1))

    def _row_col_counts(self, jogo: List[int]) -> Tuple[List[int], List[int]]:
        rows = [0] * 5
        cols = [0] * 5
        for d in jogo:
            idx = int(d) - 1
            row = idx // 5
            col = idx % 5
            rows[row] += 1
            cols[col] += 1
        return rows, cols


def build_heuristic_brains(db_conn) -> List[HeuristicPatternBrain]:
    configs = [
        HeuristicConfig(
            brain_id="heur_even_7",
            name="Heurística Paridade 7",
            category="heuristico",
            version="v1",
            constraints={"even_target": 7, "even_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_even_8",
            name="Heurística Paridade 8",
            category="heuristico",
            version="v1",
            constraints={"even_target": 8, "even_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_even_9",
            name="Heurística Paridade 9",
            category="heuristico",
            version="v1",
            constraints={"even_target": 9, "even_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_odd_7",
            name="Heurística Ímpares 7",
            category="heuristico",
            version="v1",
            constraints={"odd_target": 7, "odd_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_odd_8",
            name="Heurística Ímpares 8",
            category="heuristico",
            version="v1",
            constraints={"odd_target": 8, "odd_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_repeat_9",
            name="Heurística Repetidas 9",
            category="heuristico",
            version="v1",
            constraints={"repeat_target": 9, "repeat_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_repeat_10",
            name="Heurística Repetidas 10",
            category="heuristico",
            version="v1",
            constraints={"repeat_target": 10, "repeat_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_moldura_10",
            name="Heurística Moldura 10",
            category="heuristico",
            version="v1",
            constraints={"moldura_target": 10, "moldura_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_moldura_11",
            name="Heurística Moldura 11",
            category="heuristico",
            version="v1",
            constraints={"moldura_target": 11, "moldura_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_mult3_4",
            name="Heurística Múltiplos de 3 (4)",
            category="heuristico",
            version="v1",
            constraints={"mult3_target": 4, "mult3_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_mult3_6",
            name="Heurística Múltiplos de 3 (6)",
            category="heuristico",
            version="v1",
            constraints={"mult3_target": 6, "mult3_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_fib_3",
            name="Heurística Fibonacci 3",
            category="heuristico",
            version="v1",
            constraints={"fib_target": 3, "fib_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_fib_5",
            name="Heurística Fibonacci 5",
            category="heuristico",
            version="v1",
            constraints={"fib_target": 5, "fib_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_sum_170_210",
            name="Heurística Soma 170-210",
            category="heuristico",
            version="v1",
            constraints={"sum_range": (170, 210)},
        ),
        HeuristicConfig(
            brain_id="heur_sum_180_220",
            name="Heurística Soma 180-220",
            category="heuristico",
            version="v1",
            constraints={"sum_range": (180, 220)},
        ),
        HeuristicConfig(
            brain_id="heur_sum_190_230",
            name="Heurística Soma 190-230",
            category="heuristico",
            version="v1",
            constraints={"sum_range": (190, 230)},
        ),
        HeuristicConfig(
            brain_id="heur_low_7",
            name="Heurística Baixas 7",
            category="heuristico",
            version="v1",
            constraints={"low_target": 7, "low_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_low_8",
            name="Heurística Baixas 8",
            category="heuristico",
            version="v1",
            constraints={"low_target": 8, "low_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_low_6",
            name="Heurística Baixas 6",
            category="heuristico",
            version="v1",
            constraints={"low_target": 6, "low_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_prime_5",
            name="Heurística Primos 5",
            category="heuristico",
            version="v1",
            constraints={"prime_target": 5, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_prime_6",
            name="Heurística Primos 6",
            category="heuristico",
            version="v1",
            constraints={"prime_target": 6, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_prime_7",
            name="Heurística Primos 7",
            category="heuristico",
            version="v1",
            constraints={"prime_target": 7, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_run_4",
            name="Heurística Sequência Máx 4",
            category="heuristico",
            version="v1",
            constraints={"max_run": 4},
        ),
        HeuristicConfig(
            brain_id="heur_run_5",
            name="Heurística Sequência Máx 5",
            category="heuristico",
            version="v1",
            constraints={"max_run": 5},
        ),
        HeuristicConfig(
            brain_id="heur_run_6",
            name="Heurística Sequência Máx 6",
            category="heuristico",
            version="v1",
            constraints={"max_run": 6},
        ),
        HeuristicConfig(
            brain_id="heur_row_cap_4",
            name="Heurística Linha Máx 4",
            category="heuristico",
            version="v1",
            constraints={"row_cap": 4},
        ),
        HeuristicConfig(
            brain_id="heur_row_cap_5",
            name="Heurística Linha Máx 5",
            category="heuristico",
            version="v1",
            constraints={"row_cap": 5},
        ),
        HeuristicConfig(
            brain_id="heur_col_cap_4",
            name="Heurística Coluna Máx 4",
            category="heuristico",
            version="v1",
            constraints={"col_cap": 4},
        ),
        HeuristicConfig(
            brain_id="heur_col_cap_5",
            name="Heurística Coluna Máx 5",
            category="heuristico",
            version="v1",
            constraints={"col_cap": 5},
        ),
        HeuristicConfig(
            brain_id="heur_even8_sum180_220",
            name="Heurística Paridade 8 + Soma 180-220",
            category="heuristico",
            version="v1",
            constraints={"even_target": 8, "even_tol": 1, "sum_range": (180, 220)},
        ),
        HeuristicConfig(
            brain_id="heur_even7_low7",
            name="Heurística Paridade 7 + Baixas 7",
            category="heuristico",
            version="v1",
            constraints={"even_target": 7, "even_tol": 1, "low_target": 7, "low_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_odd7_repeat9",
            name="Heurística Ímpares 7 + Repetidas 9",
            category="heuristico",
            version="v1",
            constraints={"odd_target": 7, "odd_tol": 1, "repeat_target": 9, "repeat_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_moldura10_prime6",
            name="Heurística Moldura 10 + Primos 6",
            category="heuristico",
            version="v1",
            constraints={"moldura_target": 10, "moldura_tol": 1, "prime_target": 6, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_mult3_4_fib3",
            name="Heurística Multiplos 3 (4) + Fibonacci 3",
            category="heuristico",
            version="v1",
            constraints={"mult3_target": 4, "mult3_tol": 1, "fib_target": 3, "fib_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_even8_prime6",
            name="Heurística Paridade 8 + Primos 6",
            category="heuristico",
            version="v1",
            constraints={"even_target": 8, "even_tol": 1, "prime_target": 6, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_sum190_230_run5",
            name="Heurística Soma 190-230 + Sequência 5",
            category="heuristico",
            version="v1",
            constraints={"sum_range": (190, 230), "max_run": 5},
        ),
        HeuristicConfig(
            brain_id="heur_low8_prime6",
            name="Heurística Baixas 8 + Primos 6",
            category="heuristico",
            version="v1",
            constraints={"low_target": 8, "low_tol": 1, "prime_target": 6, "prime_tol": 1},
        ),
        HeuristicConfig(
            brain_id="heur_low7_run4",
            name="Heurística Baixas 7 + Sequência 4",
            category="heuristico",
            version="v1",
            constraints={"low_target": 7, "low_tol": 1, "max_run": 4},
        ),
        HeuristicConfig(
            brain_id="heur_row4_col4",
            name="Heurística Linha 4 + Coluna 4",
            category="heuristico",
            version="v1",
            constraints={"row_cap": 4, "col_cap": 4},
        ),
        HeuristicConfig(
            brain_id="heur_row5_col5",
            name="Heurística Linha 5 + Coluna 5",
            category="heuristico",
            version="v1",
            constraints={"row_cap": 5, "col_cap": 5},
        ),
        HeuristicConfig(
            brain_id="heur_even9_sum200_240",
            name="Heurística Paridade 9 + Soma 200-240",
            category="heuristico",
            version="v1",
            constraints={"even_target": 9, "even_tol": 1, "sum_range": (200, 240)},
        ),
        HeuristicConfig(
            brain_id="heur_prime7_run5",
            name="Heurística Primos 7 + Sequência 5",
            category="heuristico",
            version="v1",
            constraints={"prime_target": 7, "prime_tol": 1, "max_run": 5},
        ),
        HeuristicConfig(
            brain_id="heur_low6_prime5_sum170_210",
            name="Heurística Baixas 6 + Primos 5 + Soma 170-210",
            category="heuristico",
            version="v1",
            constraints={"low_target": 6, "low_tol": 1, "prime_target": 5, "prime_tol": 1, "sum_range": (170, 210)},
        ),
        HeuristicConfig(
            brain_id="heur_even7_row4",
            name="Heurística Paridade 7 + Linha 4",
            category="heuristico",
            version="v1",
            constraints={"even_target": 7, "even_tol": 1, "row_cap": 4},
        ),
        HeuristicConfig(
            brain_id="heur_even8_col4",
            name="Heurística Paridade 8 + Coluna 4",
            category="heuristico",
            version="v1",
            constraints={"even_target": 8, "even_tol": 1, "col_cap": 4},
        ),
        HeuristicConfig(
            brain_id="heur_sum175_215_run4",
            name="Heurística Soma 175-215 + Sequência 4",
            category="heuristico",
            version="v1",
            constraints={"sum_range": (175, 215), "max_run": 4},
        ),
        HeuristicConfig(
            brain_id="heur_low8_sum185_225",
            name="Heurística Baixas 8 + Soma 185-225",
            category="heuristico",
            version="v1",
            constraints={"low_target": 8, "low_tol": 1, "sum_range": (185, 225)},
        ),
        HeuristicConfig(
            brain_id="heur_prime6_sum180_220",
            name="Heurística Primos 6 + Soma 180-220",
            category="heuristico",
            version="v1",
            constraints={"prime_target": 6, "prime_tol": 1, "sum_range": (180, 220)},
        ),
    ]
    return [HeuristicPatternBrain(db_conn, cfg) for cfg in configs]
