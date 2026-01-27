from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from training.core.brain_hub import BrainHub
from training.fechamentos_posicionais.auto_select import rank_numbers_with_brains, score_games_with_brains
from training.fechamentos_posicionais.types import FechamentoPosicionalSpec


@dataclass(frozen=True)
class GroupPlan:
    groups: List[List[int]]
    metadata: Dict[str, Any]


def build_groups(
    variaveis: Sequence[int],
    distribution: Sequence[int],
    rng: random.Random,
) -> GroupPlan:
    total_needed = sum(distribution)
    vars_list = list(variaveis)
    metadata: Dict[str, Any] = {}

    if total_needed != len(vars_list):
        metadata["group_adjustment"] = {
            "requested_total": total_needed,
            "available": len(vars_list),
        }

    groups: List[List[int]] = []
    index = 0
    sizes = list(distribution)
    if total_needed < len(vars_list):
        sizes.append(len(vars_list) - total_needed)
        metadata["group_adjustment"]["extra_group"] = sizes[-1]
    elif total_needed > len(vars_list):
        diff = total_needed - len(vars_list)
        metadata["group_adjustment"]["reduced"] = diff
        for i in range(len(sizes)):
            if diff <= 0:
                break
            reducible = max(0, sizes[i] - 1)
            if reducible:
                reduce_by = min(diff, reducible)
                sizes[i] -= reduce_by
                diff -= reduce_by

    for size in sizes:
        if size <= 0:
            continue
        groups.append(sorted(vars_list[index : index + size]))
        index += size

    return GroupPlan(groups=groups, metadata=metadata)


def snake_draft_groups(
    variaveis: Sequence[int],
    distribution: Sequence[int],
) -> List[List[int]]:
    groups = [[] for _ in distribution]
    order = list(range(len(groups)))
    direction = 1
    idx = 0
    for num in variaveis:
        groups[order[idx]].append(num)
        idx += direction
        if idx >= len(order):
            direction = -1
            idx = len(order) - 1
        elif idx < 0:
            direction = 1
            idx = 0
    return [sorted(g) for g in groups if g]


def plan_groups(
    spec: FechamentoPosicionalSpec,
    pool: Sequence[int],
    fixed: Sequence[int],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
) -> GroupPlan:
    rng = rng or random.Random()
    context = dict(context or {})
    variaveis = [n for n in pool if n not in set(fixed)]

    ranking = rank_numbers_with_brains(brain_hub, variaveis, context=context, size=spec.game_size)
    ranked_vars = [num for num, _ in ranking]

    groups = snake_draft_groups(ranked_vars, spec.group_distribution)
    group_plan = build_groups([n for g in groups for n in g], spec.group_distribution, rng)
    group_plan.metadata["ranking"] = ranking

    return group_plan


def _jaccard(a: Sequence[int], b: Sequence[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def _generate_games_one_per_group(
    groups: List[List[int]],
    picks_needed: int,
    rng: random.Random,
    limit: int,
) -> List[List[int]]:
    games: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()

    for _ in range(limit):
        picks: List[int] = []
        for group in groups:
            if group:
                picks.append(rng.choice(group))
        if len(picks) < picks_needed:
            remaining = [n for g in groups for n in g if n not in picks]
            picks.extend(rng.sample(remaining, min(picks_needed - len(picks), len(remaining))))
        if len(picks) > picks_needed:
            picks = rng.sample(picks, picks_needed)
        key = tuple(sorted(picks))
        if key in seen:
            continue
        seen.add(key)
        games.append(sorted(picks))
    return games


def _generate_games_full_groups(
    groups: List[List[int]],
    picks_needed: int,
    rng: random.Random,
    limit: int,
) -> List[List[int]]:
    games: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()
    flat = [n for g in groups for n in g]

    for _ in range(limit):
        picks: List[int] = []
        group_order = list(range(len(groups)))
        rng.shuffle(group_order)
        for idx in group_order:
            if len(picks) >= picks_needed:
                break
            picks.extend(groups[idx])
        if len(picks) < picks_needed:
            remaining = [n for n in flat if n not in picks]
            picks.extend(rng.sample(remaining, min(picks_needed - len(picks), len(remaining))))
        if len(picks) > picks_needed:
            picks = rng.sample(picks, picks_needed)
        key = tuple(sorted(picks))
        if key in seen:
            continue
        seen.add(key)
        games.append(sorted(picks))
    return games


def _generate_games_top_score(
    ranking: Sequence[Tuple[int, float]],
    picks_needed: int,
    rng: random.Random,
    limit: int,
) -> List[List[int]]:
    ordered = [num for num, _ in ranking]
    games: List[List[int]] = []
    seen: set[Tuple[int, ...]] = set()

    for _ in range(limit):
        top_slice = ordered[: max(picks_needed + 2, min(len(ordered), picks_needed + 6))]
        picks = rng.sample(top_slice, picks_needed)
        key = tuple(sorted(picks))
        if key in seen:
            continue
        seen.add(key)
        games.append(sorted(picks))
    return games


def plan_policy(
    spec: FechamentoPosicionalSpec,
    groups: List[List[int]],
    fixed: Sequence[int],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    samples_per_policy: int = 200,
) -> Tuple[str, List[List[int]], Dict[str, Any]]:
    rng = rng or random.Random()
    context = dict(context or {})
    picks_needed = spec.game_size - len(fixed)

    ranking = rank_numbers_with_brains(brain_hub, [n for g in groups for n in g], context=context, size=spec.game_size)

    policies = {
        "one_per_group": _generate_games_one_per_group,
        "full_groups": _generate_games_full_groups,
        "top_score": lambda g, p, r, l: _generate_games_top_score(ranking, p, r, l),
    }

    scored_policies = []
    for name, builder in policies.items():
        if name == "top_score":
            games = builder(groups, picks_needed, rng, samples_per_policy)
        else:
            games = builder(groups, picks_needed, rng, samples_per_policy)
        if not games:
            continue
        full_games = [sorted(list(fixed) + game) for game in games]
        scores = score_games_with_brains(brain_hub, full_games, context=context)
        avg_score = sum(scores) / max(1, len(scores))
        diversity = 1.0
        if len(full_games) > 1:
            diversity = 1.0 - max(_jaccard(full_games[0], g) for g in full_games[1:])
        scored_policies.append((name, avg_score + 0.2 * diversity, games))

    if not scored_policies:
        fallback_games = _generate_games_one_per_group(groups, picks_needed, rng, samples_per_policy)
        return "one_per_group", fallback_games, {"policy_fallback": True}

    scored_policies.sort(key=lambda x: x[1], reverse=True)
    name, score, games = scored_policies[0]
    return name, games, {"policy_score": score}
