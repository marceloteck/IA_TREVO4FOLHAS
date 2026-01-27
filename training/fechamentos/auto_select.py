from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from training.core.brain_hub import BrainHub
from training.fechamentos.generator import score_games_with_brains
from training.fechamentos.types import FechamentoSpec


@dataclass(frozen=True)
class AutoSelectConfig:
    candidate_pools: int = 400
    pool_samples: int = 40
    max_random_swaps: int = 6


def _normalize_scores(values: List[float]) -> List[float]:
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5 for _ in values]
    return [(v - min_v) / (max_v - min_v) for v in values]


def rank_numbers_with_brains(
    brain_hub: BrainHub,
    universe: Sequence[int],
    context: Optional[Dict[str, Any]] = None,
    per_brain: int = 80,
    size: int = 15,
) -> List[Tuple[int, float]]:
    context = dict(context or {})
    scores: Dict[int, float] = {n: 0.0 for n in universe}

    for brain in getattr(brain_hub, "brains", []):
        if not getattr(brain, "enabled", True):
            continue
        rel = float(brain.evaluate_context(context))
        if rel <= 0:
            continue

        games = brain.generate(context=context, size=int(size), n=int(per_brain))
        if not games:
            continue

        raw_scores = [float(brain.score_game(game, context)) for game in games]
        normalized = _normalize_scores(raw_scores)
        meta_weight = getattr(brain_hub, "_meta_weight", lambda _: 1.0)(str(brain.id))

        for game, norm in zip(games, normalized):
            score = (norm * 0.65 + rel * 0.35) * float(meta_weight)
            for dezena in game:
                if dezena in scores:
                    scores[dezena] += score

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked


def _sample_games_from_pool(
    pool: Sequence[int],
    game_size: int,
    rng: random.Random,
    samples: int,
) -> List[List[int]]:
    if len(pool) < game_size:
        return []
    games: List[List[int]] = []
    for _ in range(samples):
        game = sorted(rng.sample(list(pool), game_size))
        games.append(game)
    return games


def _score_pool(
    pool: Sequence[int],
    game_size: int,
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]],
    rng: random.Random,
    samples: int,
) -> float:
    games = _sample_games_from_pool(pool, game_size, rng, samples)
    if not games:
        return 0.0
    scores = score_games_with_brains(brain_hub, games, context=context)
    avg_score = sum(scores) / max(1, len(scores))
    max_score = max(scores) if scores else 0.0
    return 0.7 * avg_score + 0.3 * max_score


def pick_pool_and_fixed(
    spec: FechamentoSpec,
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    config: Optional[AutoSelectConfig] = None,
) -> Tuple[List[int], List[int], Dict[str, Any]]:
    rng = rng or random.Random()
    config = config or AutoSelectConfig()
    context = dict(context or {})

    universe = list(range(1, 26))
    ranked = rank_numbers_with_brains(brain_hub, universe, context=context, size=spec.game_size)
    ranked_numbers = [num for num, _ in ranked]

    candidate_pools: List[List[int]] = []
    base_pool = ranked_numbers[: spec.total_numbers]

    for _ in range(config.candidate_pools):
        pool = list(base_pool)
        swap_count = rng.randint(0, min(config.max_random_swaps, len(universe) - spec.total_numbers))
        if swap_count > 0:
            pool_set = set(pool)
            available = [n for n in universe if n not in pool_set]
            for _ in range(swap_count):
                remove = rng.choice(pool)
                pool.remove(remove)
                pool_set.remove(remove)
                add = rng.choice(available)
                available.remove(add)
                pool.append(add)
                pool_set.add(add)
        candidate_pools.append(sorted(pool))

    scored_pools = []
    for pool in candidate_pools:
        score = _score_pool(pool, spec.game_size, brain_hub, context, rng, config.pool_samples)
        scored_pools.append((pool, score))

    scored_pools.sort(key=lambda x: x[1], reverse=True)
    best_pool = scored_pools[0][0] if scored_pools else sorted(base_pool)

    fixed = []
    fixed_meta: Dict[str, Any] = {}
    if spec.fixed_required_count > 0:
        ranking = rank_numbers_with_brains(brain_hub, best_pool, context=context, size=spec.game_size)
        fixed = [num for num, _ in ranking[: spec.fixed_required_count]]
        fixed_meta["ranking"] = ranking

    metadata = {
        "pool_candidates": len(candidate_pools),
        "pool_score": scored_pools[0][1] if scored_pools else 0.0,
        "ranking": ranked,
        "fixed": fixed_meta,
    }

    return sorted(best_pool), sorted(fixed), metadata
