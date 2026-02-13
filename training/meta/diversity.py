from __future__ import annotations

import random
from itertools import combinations


def jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    if not u:
        return 1.0
    return len(a & b) / float(len(u))


def portfolio_diversity(games: list[list[int]], pair_sample_max: int = 200) -> float:
    clean_sets = [set(int(x) for x in g if x is not None) for g in games if g]
    if len(clean_sets) <= 1:
        return 0.0

    pairs = list(combinations(range(len(clean_sets)), 2))
    if len(pairs) > int(pair_sample_max):
        pairs = random.sample(pairs, int(pair_sample_max))

    distances = []
    for i, j in pairs:
        distances.append(1.0 - jaccard(clean_sets[i], clean_sets[j]))

    if not distances:
        return 0.0
    return max(0.0, min(1.0, sum(distances) / float(len(distances))))
