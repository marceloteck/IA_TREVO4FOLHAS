from __future__ import annotations

import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from training.core.base_brain import BaseBrain


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _wrap_number(value: int, max_value: int = 25) -> int:
    return ((value - 1) % max_value) + 1


def _pattern_id(base_id: str, size: int) -> str:
    return f"{base_id}-s{size}"


BASE_PATTERNS: List[Tuple[str, List[int]]] = [
    ("P1", [2, 2, 1, 2, 1, 1, 2, 2, 1, 2, 1, 1, 2, 2]),
    ("P2", [1, 2, 2, 1, 1, 2, 2, 1, 2, 1, 2, 1, 1, 2]),
    ("P3", [2, 1, 2, 1, 2, 2, 1, 2, 1, 2, 1, 2, 2, 1]),
    ("P4", [1, 1, 2, 2, 1, 2, 1, 2, 2, 1, 2, 1, 2, 1]),
    ("P5", [2, 1, 1, 2, 2, 1, 2, 1, 1, 2, 2, 1, 2, 1]),
    ("P6", [1, 2, 1, 2, 1, 1, 2, 3, 1, 2, 1, 1, 2, 3]),
    ("P7", [2, 1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 1, 2, 1]),
    ("P8", [1, 2, 1, 1, 2, 2, 1, 3, 1, 2, 2, 1, 1, 2]),
    ("P9", [2, 2, 1, 3, 1, 2, 1, 2, 1, 3, 1, 2, 2, 1]),
    ("P10", [1, 2, 2, 1, 2, 1, 3, 1, 2, 1, 2, 2, 1, 2]),
    ("P11", [2, 1, 2, 2, 1, 1, 3, 1, 2, 1, 2, 1, 2, 1]),
    ("P12", [1, 3, 1, 2, 1, 2, 1, 2, 2, 1, 1, 2, 1, 2]),
]


class HeuristicStepSequencesBrain(BaseBrain):
    """
    Brain heurístico baseado em sequências de passos (delta sequences).
    - Gera jogos com start + deltas (wrap 1..25).
    - Aplica mutação leve e exploração controlada.
    - Aprende padrões simples via estado persistido.
    """

    def __init__(
        self,
        db_conn,
        mutation_rate: float = 0.10,
        exploration_rate: float = 0.10,
        delta_max: int = 3,
        wrap_mode: str = "wrap",
        max_attempts_per_game: int = 50,
        min_twos: Optional[int] = None,
        version: str = "v1",
    ) -> None:
        super().__init__(
            db_conn=db_conn,
            brain_id="heur_step_sequences",
            name="Heur - Step Sequences",
            category="heuristico",
            version=version,
        )
        self.mutation_rate = float(mutation_rate)
        self.exploration_rate = float(exploration_rate)
        self.delta_max = max(2, int(delta_max))
        self.wrap_mode = str(wrap_mode)
        self.max_attempts_per_game = max(10, int(max_attempts_per_game))
        self.min_twos = min_twos

        self._recent_meta: Dict[Tuple[int, ...], Dict[str, Any]] = {}

        self.load_state()
        self.state = self.state or {}
        self.state.setdefault("pattern_stats", {})
        self.state.setdefault("last_updated", None)

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        historico = context.get("historico_recente") or []
        base = 0.6
        if len(historico) >= 60:
            base = 0.75
        if len(historico) >= 150:
            base = 0.9
        return min(0.95, base)

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18, 19):
            size = 15

        jogos: List[List[int]] = []
        attempts = 0
        max_attempts = max(10, n * self.max_attempts_per_game)

        while len(jogos) < n and attempts < max_attempts:
            attempts += 1
            result = self._build_candidate(size=size, context=context)
            if result is None:
                continue
            jogo, meta = result
            if not self._passes_filters(jogo=jogo, size=size, context=context, deltas=meta.get("deltas")):
                continue
            jogos.append(jogo)
            self._track_meta(jogo, meta)

        while len(jogos) < n:
            result = self._build_candidate(size=size, context=context, relax=True)
            if result is None:
                continue
            jogo, meta = result
            jogos.append(jogo)
            self._track_meta(jogo, meta)

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        meta = self._recent_meta.get(tuple(jogo), {})
        pattern_id = meta.get("pattern_id")
        if not pattern_id:
            return 0.4

        stats = self.state.get("pattern_stats", {}).get(pattern_id, {})
        avg_score = float(stats.get("avg_score", 0.0))
        top_hits = int(stats.get("top_hits", 0))
        best_hits = int(stats.get("best_hits", 0))

        base = 0.35 + min(0.6, avg_score / 15.0)
        bonus = min(0.2, 0.02 * top_hits + 0.01 * best_hits)
        return min(1.0, base + bonus)

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        meta = self._recent_meta.get(tuple(jogo))
        if not meta:
            self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)
            return

        pattern_id = meta.get("pattern_id")
        if pattern_id:
            stats = self.state.setdefault("pattern_stats", {}).setdefault(
                pattern_id,
                {"uses": 0, "top_hits": 0, "avg_score": 0.0, "best_hits": 0, "score_count": 0},
            )
            if int(pontos) >= 14:
                stats["top_hits"] = int(stats.get("top_hits", 0)) + 1
            if int(pontos) >= 13:
                stats["best_hits"] = int(stats.get("best_hits", 0)) + 1

            score_count = int(stats.get("score_count", 0)) + 1
            avg_score = float(stats.get("avg_score", 0.0))
            avg_score = (avg_score * (score_count - 1) + float(pontos)) / score_count
            stats["avg_score"] = float(avg_score)
            stats["score_count"] = score_count

            self.state["pattern_stats"][pattern_id] = stats
            self.state["last_updated"] = _now()

        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    def _build_candidate(
        self,
        size: int,
        context: Dict[str, Any],
        relax: bool = False,
    ) -> Optional[Tuple[List[int], Dict[str, Any]]]:
        base_id, deltas = self._pick_pattern(size=size)
        if not deltas:
            return None

        mutation = False
        if random.random() < self.mutation_rate:
            deltas = self._mutate_deltas(deltas)
            mutation = True

        start = random.randint(1, 25)
        numbers = self._sequence_from_deltas(start=start, deltas=deltas, size=size)
        if not numbers or len(numbers) != size:
            return None

        jogo = sorted(numbers)
        pattern_id = _pattern_id(base_id, size)
        meta = {
            "pattern_id": pattern_id,
            "start": start,
            "mutation": mutation,
            "relax": relax,
            "deltas": list(deltas),
        }

        stats = self.state.setdefault("pattern_stats", {}).setdefault(
            pattern_id,
            {"uses": 0, "top_hits": 0, "avg_score": 0.0, "best_hits": 0, "score_count": 0},
        )
        stats["uses"] = int(stats.get("uses", 0)) + 1
        self.state["pattern_stats"][pattern_id] = stats
        self.state["last_updated"] = _now()

        return jogo, meta

    def _pick_pattern(self, size: int) -> Tuple[str, List[int]]:
        patterns = BASE_PATTERNS
        if not patterns:
            return "", []

        if random.random() < self.exploration_rate:
            base_id, base = random.choice(patterns)
            return base_id, self._expand_pattern(base, size - 1)

        weights = []
        for base_id, _ in patterns:
            pid = _pattern_id(base_id, size)
            stats = self.state.get("pattern_stats", {}).get(pid, {})
            top_hits = int(stats.get("top_hits", 0))
            best_hits = int(stats.get("best_hits", 0))
            avg_score = float(stats.get("avg_score", 0.0))
            weight = 1.0 + top_hits * 0.4 + best_hits * 0.2 + avg_score * 0.03
            weights.append(weight)

        base_id, base = random.choices(patterns, weights=weights, k=1)[0]
        return base_id, self._expand_pattern(base, size - 1)

    def _expand_pattern(self, base: List[int], steps: int) -> List[int]:
        if steps <= 0:
            return []
        expanded: List[int] = []
        idx = 0
        while len(expanded) < steps:
            expanded.append(int(base[idx % len(base)]))
            idx += 1
        return [max(1, min(self.delta_max, int(x))) for x in expanded[:steps]]

    def _mutate_deltas(self, deltas: List[int]) -> List[int]:
        mutated = list(deltas)
        positions = random.randint(1, 3)
        for _ in range(positions):
            idx = random.randrange(len(mutated))
            current = mutated[idx]
            if current == 1:
                mutated[idx] = 2 if self.delta_max >= 2 else 1
            elif current == 2:
                mutated[idx] = 1
            else:
                mutated[idx] = random.randint(1, self.delta_max)
        return [max(1, min(self.delta_max, int(x))) for x in mutated]

    def _sequence_from_deltas(self, start: int, deltas: List[int], size: int) -> Optional[List[int]]:
        nums = [int(start)]
        for d in deltas:
            nxt = nums[-1] + int(d)
            if self.wrap_mode == "wrap":
                nxt = _wrap_number(nxt, 25)
            else:
                nxt = _wrap_number(nxt, 25)

            if nxt in nums:
                found = False
                candidate = nxt
                for _ in range(25):
                    candidate = _wrap_number(candidate + 1, 25)
                    if candidate not in nums:
                        nxt = candidate
                        found = True
                        break
                if not found:
                    return None

            nums.append(nxt)
            if len(nums) >= size:
                break

        if len(set(nums)) != size:
            return None
        return nums[:size]

    def _passes_filters(
        self,
        jogo: List[int],
        size: int,
        context: Dict[str, Any],
        deltas: Optional[List[int]] = None,
    ) -> bool:
        if len(jogo) != size or len(set(jogo)) != size:
            return False

        min_twos = self.min_twos
        if min_twos is None:
            min_twos = 3 if size == 15 else 4
        if deltas:
            steps_twos = sum(1 for d in deltas if int(d) == 2)
            if steps_twos < min_twos:
                return False

        ran_check = context.get("ran_check")
        if callable(ran_check) and not ran_check(jogo):
            return False

        core_check = context.get("core_protect_check")
        if callable(core_check) and not core_check(jogo):
            return False

        return True

    def _track_meta(self, jogo: List[int], meta: Dict[str, Any]) -> None:
        key = tuple(jogo)
        self._recent_meta[key] = meta
        if os.getenv("DEBUG_STEPS") == "1":
            print(
                f"[heur_step_sequences] jogo={key} pattern={meta.get('pattern_id')} start={meta.get('start')} mutation={meta.get('mutation')}"
            )
        if len(self._recent_meta) > 4000:
            for old_key in list(self._recent_meta.keys())[:1000]:
                self._recent_meta.pop(old_key, None)
