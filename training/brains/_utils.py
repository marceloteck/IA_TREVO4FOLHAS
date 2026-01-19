# training/brains/_utils.py
from __future__ import annotations
import random
from typing import Dict, List

UNIVERSO = list(range(1, 26))

def weighted_sample_without_replacement(weights: Dict[int, float], k: int) -> List[int]:
    # método simples e leve: amostra repetida sem reposição
    pool = UNIVERSO[:]
    result = []
    for _ in range(k):
        w = [max(0.0001, float(weights.get(x, 0.001))) for x in pool]
        pick = random.choices(pool, weights=w, k=1)[0]
        result.append(pick)
        pool.remove(pick)
    return sorted(result)

def count_even(jogo: List[int]) -> int:
    return sum(1 for x in jogo if x % 2 == 0)

def max_consecutive_run(jogo: List[int]) -> int:
    s = sorted(jogo)
    best = cur = 1
    for i in range(1, len(s)):
        if s[i] == s[i-1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best
