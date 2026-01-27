from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from training.core.brain_hub import BrainHub
from training.fechamentos_posicionais.grouping import plan_policy
from training.fechamentos_posicionais.types import FechamentoPosicionalResult, FechamentoPosicionalSpec
from training.fechamentos_posicionais.validate import validate_fechamento_output


_PRIMES = {2, 3, 5, 7, 11, 13, 17, 19, 23}


@dataclass(frozen=True)
class GameCandidate:
    game: List[int]


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


def _jaccard(a: Sequence[int], b: Sequence[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


def select_top_diverse(
    games: List[List[int]],
    pool: Sequence[int],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]],
    k: int,
    w_score: float = 0.7,
    w_diversity: float = 0.3,
) -> List[List[int]]:
    if not games:
        return []
    scores = score_games_with_brains(brain_hub, games, context=context)
    norm_scores = _normalize_scores(scores)

    selected: List[List[int]] = []
    usage_counts = {n: 0 for n in pool}
    remaining = list(zip(games, norm_scores))

    def diversity_bonus(candidate: List[int]) -> float:
        if not selected:
            return 1.0
        max_j = max(_jaccard(candidate, s) for s in selected)
        jaccard_bonus = 1.0 - max_j
        coverage_values = [1.0 / (1.0 + usage_counts.get(num, 0)) for num in candidate]
        coverage_bonus = sum(coverage_values) / max(1, len(coverage_values))
        return 0.6 * jaccard_bonus + 0.4 * coverage_bonus

    while remaining and len(selected) < k:
        best_idx = 0
        best_score = -1.0
        for idx, (game, score) in enumerate(remaining):
            total = w_score * score + w_diversity * diversity_bonus(game)
            if total > best_score:
                best_score = total
                best_idx = idx
        game, _ = remaining.pop(best_idx)
        selected.append(game)
        for num in game:
            usage_counts[num] = usage_counts.get(num, 0) + 1

    return selected


def generate_fechamento(
    spec: FechamentoPosicionalSpec,
    pool: Sequence[int],
    fixed: Sequence[int],
    groups: List[List[int]],
    brain_hub: BrainHub,
    context: Optional[Dict[str, Any]] = None,
    rng: Optional[random.Random] = None,
    selection_metadata: Optional[Dict[str, Any]] = None,
) -> FechamentoPosicionalResult:
    context = dict(context or {})
    rng = rng or random.Random()

    policy_name, policy_games, policy_meta = plan_policy(
        spec,
        groups,
        fixed,
        brain_hub,
        context=context,
        rng=rng,
    )

    full_games = [sorted(list(fixed) + game) for game in policy_games]
    selected_games = select_top_diverse(
        full_games,
        pool,
        brain_hub,
        context=context,
        k=spec.games_count,
    )

    scores = score_games_with_brains(brain_hub, selected_games, context=context)
    jogos_rankeados = []
    for game, score in zip(selected_games, scores):
        tags = compute_game_tags(game, context)
        jogos_rankeados.append({"jogo": game, "score": float(score), "tags": tags})

    jogos_rankeados.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)

    metadata = {
        "spec": spec.__dict__,
        "policy": policy_name,
        "garantia_declarada": (
            "garantia declarada do fechamento (modelo combinatório); produto estatístico e informativo; "
            "loterias envolvem aleatoriedade; não existe garantia de prêmio"
        ),
        "policy_meta": policy_meta,
    }
    if selection_metadata:
        metadata["selecao"] = selection_metadata
    if spec.condition_text:
        metadata["condition_text"] = spec.condition_text

    result = FechamentoPosicionalResult(
        pool=sorted(pool),
        fixed=sorted(fixed),
        groups=[sorted(g) for g in groups],
        jogos=selected_games,
        jogos_rankeados=jogos_rankeados,
        metadata=metadata,
    )

    validate_fechamento_output(spec, result)
    return result
