from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from training.core.brain_hub import BrainHub
from training.fechamentos.types import FechamentoResult, FechamentoSpec
from training.fechamentos.validate import validate_fechamento_output


_PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23}


@dataclass(frozen=True)
class GameCandidate:
    game: List[int]
    removed_numbers: Tuple[int, ...]


def compute_game_tags(game: Sequence[int], context: Dict[str, Any]) -> Dict[str, Any]:
    evens = sum(1 for n in game if n % 2 == 0)
    odds = len(game) - evens
    total = sum(game)
    primes = sum(1 for n in game if n in _PRIMES)

    tags = {
        "paridade": {"pares": evens, "impares": odds},
        "soma": total,
        "primos": primes,
    }

    ultimo_resultado = context.get("ultimo_resultado")
    if ultimo_resultado:
        repetidas = len(set(game) & set(int(x) for x in ultimo_resultado))
        tags["repetidas"] = repetidas

    return tags


def _normalize_scores(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5 for _ in values]
    return [(v - min_v) / (max_v - min_v) for v in values]


def score_games_with_brains(
    brain_hub: BrainHub,
    games: List[List[int]],
    context: Optional[Dict[str, Any]] = None,
) -> List[float]:
    context = dict(context or {})
    totals = [0.0 for _ in games]

    for brain in getattr(brain_hub, "brains", []):
        if not getattr(brain, "enabled", True):
            continue
        rel = float(brain.evaluate_context(context))
        if rel <= 0:
            continue

        raw_scores = [float(brain.score_game(game, context)) for game in games]
        normalized = _normalize_scores(raw_scores)
        meta_weight = getattr(brain_hub, "_meta_weight", lambda _: 1.0)(str(brain.id))

        for idx, norm in enumerate(normalized):
            totals[idx] += (norm * 0.65 + rel * 0.35) * float(meta_weight)

    return totals


def generate_game_candidates(
    pool: Sequence[int],
    fixed: Sequence[int],
    game_size: int,
    rng: random.Random,
    max_candidates: int = 30000,
) -> List[GameCandidate]:
    fixed_set = set(fixed)
    variable_pool = [n for n in pool if n not in fixed_set]
    need_from_pool = game_size - len(fixed_set)
    remove_count = len(variable_pool) - need_from_pool

    if remove_count < 0:
        raise ValueError("Configuração inválida: fixas maiores que o tamanho do jogo.")

    total_combos = 1
    if remove_count > 0:
        total_combos = len(list(combinations(range(len(variable_pool)), remove_count)))

    candidates: List[GameCandidate] = []
    seen: Set[Tuple[int, ...]] = set()

    def add_candidate(removed_indices: Tuple[int, ...]) -> None:
        removed_numbers = tuple(sorted(variable_pool[i] for i in removed_indices))
        game_numbers = [n for idx, n in enumerate(variable_pool) if idx not in removed_indices]
        game = sorted(list(fixed_set) + game_numbers)
        key = tuple(game)
        if key in seen:
            return
        seen.add(key)
        candidates.append(GameCandidate(game=game, removed_numbers=removed_numbers))

    if remove_count == 0:
        add_candidate(tuple())
        return candidates

    if total_combos <= max_candidates:
        for combo in combinations(range(len(variable_pool)), remove_count):
            add_candidate(combo)
        return candidates

    attempts = 0
    while len(candidates) < max_candidates and attempts < max_candidates * 5:
        removed_indices = tuple(sorted(rng.sample(range(len(variable_pool)), remove_count)))
        add_candidate(removed_indices)
        attempts += 1

    return candidates


def _jaccard(a: Sequence[int], b: Sequence[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def select_top_diverse(
    candidates: List[GameCandidate],
    k: int,
    pool: Sequence[int],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    w_score: float = 0.7,
    w_diversity: float = 0.3,
) -> List[GameCandidate]:
    if not candidates:
        return []

    games = [c.game for c in candidates]
    base_scores = score_games_with_brains(brain_hub, games, context=context)
    norm_scores = _normalize_scores(base_scores)

    selected: List[GameCandidate] = []
    usage_counts = {n: 0 for n in pool}
    removed_counts: Dict[Tuple[int, ...], int] = {}

    remaining = list(zip(candidates, norm_scores))

    def diversity_bonus(candidate: GameCandidate) -> float:
        if not selected:
            return 1.0
        max_j = max(_jaccard(candidate.game, s.game) for s in selected)
        jaccard_bonus = 1.0 - max_j

        coverage_values = []
        for num in candidate.game:
            coverage_values.append(1.0 / (1.0 + usage_counts.get(num, 0)))
        coverage_bonus = sum(coverage_values) / max(1, len(coverage_values))

        removed_count = removed_counts.get(candidate.removed_numbers, 0)
        removed_bonus = 1.0 / (1.0 + removed_count)

        return 0.5 * jaccard_bonus + 0.3 * coverage_bonus + 0.2 * removed_bonus

    while remaining and len(selected) < k:
        best_idx = 0
        best_score = -1.0
        for idx, (candidate, score) in enumerate(remaining):
            bonus = diversity_bonus(candidate)
            total = w_score * score + w_diversity * bonus
            if total > best_score:
                best_score = total
                best_idx = idx

        candidate, _ = remaining.pop(best_idx)
        selected.append(candidate)
        removed_counts[candidate.removed_numbers] = removed_counts.get(candidate.removed_numbers, 0) + 1
        for num in candidate.game:
            usage_counts[num] = usage_counts.get(num, 0) + 1

    return selected


def generate_fechamento(
    spec: FechamentoSpec,
    pool: Sequence[int],
    fixed: Sequence[int],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    max_candidates: int = 30000,
    selection_metadata: Optional[Dict[str, Any]] = None,
) -> FechamentoResult:
    context = dict(context or {})
    rng = rng or random.Random()

    candidates = generate_game_candidates(pool, fixed, spec.game_size, rng, max_candidates=max_candidates)
    selected = select_top_diverse(
        candidates,
        spec.games_count,
        pool,
        brain_hub,
        context=context,
    )

    games = [candidate.game for candidate in selected]
    scores = score_games_with_brains(brain_hub, games, context=context)

    jogos_rankeados = []
    for game, score in zip(games, scores):
        tags = compute_game_tags(game, context)
        jogos_rankeados.append({"jogo": game, "score": float(score), "tags": tags})

    jogos_rankeados.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

    metadata = {
        "spec": spec.__dict__,
        "garantia_declarada": (
            "garantia declarada do fechamento (modelo combinatório); produto estatístico, "
            "loteria é aleatória; não há garantia de prêmio"
        ),
    }
    if selection_metadata:
        metadata["selecao"] = selection_metadata

    result = FechamentoResult(
        pool=sorted(pool),
        fixed=sorted(fixed),
        jogos=games,
        jogos_rankeados=jogos_rankeados,
        metadata=metadata,
    )

    validate_fechamento_output(spec, result)
    return result
