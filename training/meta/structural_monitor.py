from __future__ import annotations

from collections import Counter
import math
from typing import Dict, List


def _entropy_norm(values: List[float]) -> float:
    vals = [float(v) for v in values if float(v) > 0.0]
    if not vals:
        return 0.0
    total = sum(vals)
    if total <= 0.0:
        return 0.0
    probs = [v / total for v in vals]
    h = -sum(p * math.log(p + 1e-12, 2) for p in probs)
    hmax = math.log(max(2, len(probs)), 2)
    return max(0.0, min(1.0, h / hmax if hmax > 0 else 0.0))


def _line_col_bucket(game: List[int]) -> str:
    lines = [0, 0, 0, 0, 0]
    cols = [0, 0, 0, 0, 0]
    for d in game:
        x = int(d)
        if x < 1 or x > 25:
            continue
        line = (x - 1) // 5
        col = (x - 1) % 5
        lines[line] += 1
        cols[col] += 1
    return f"L:{','.join(str(x) for x in lines)}|C:{','.join(str(x) for x in cols)}"


def calcular_entropia_estrutural(jogos: List[List[int]]) -> float:
    if not jogos:
        return 0.0

    parity = Counter()
    sums = Counter()
    repeated = Counter()
    line_col = Counter()

    prev: set[int] = set(jogos[0]) if jogos else set()
    for g in jogos:
        game = sorted(set(int(x) for x in g if x is not None))
        if not game:
            continue
        ev = sum(1 for d in game if d % 2 == 0)
        parity[ev] += 1

        s = sum(game)
        sb = int(s // 15)
        sums[sb] += 1

        rep = len(set(game) & prev) if prev else 0
        repeated[rep] += 1

        line_col[_line_col_bucket(game)] += 1
        prev = set(game)

    h_parity = _entropy_norm(list(parity.values()))
    h_sums = _entropy_norm(list(sums.values()))
    h_repeated = _entropy_norm(list(repeated.values()))
    h_line_col = _entropy_norm(list(line_col.values()))
    return max(0.0, min(1.0, (h_parity + h_sums + h_repeated + h_line_col) / 4.0))


def calcular_clone_ratio(jogos: List[List[int]]) -> float:
    if not jogos or len(jogos) <= 1:
        return 0.0
    sets = [set(int(x) for x in g if x is not None) for g in jogos]
    sims = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            uni = len(sets[i] | sets[j])
            if uni <= 0:
                continue
            sims.append(len(sets[i] & sets[j]) / float(uni))
    if not sims:
        return 0.0
    return max(0.0, min(1.0, sum(sims) / float(len(sims))))


def cobertura_pares(jogos: List[List[int]]) -> float:
    if not jogos:
        return 0.0
    covered = set()
    universo = set(range(1, 26))
    total_pairs = len(universo) * (len(universo) - 1) // 2
    for g in jogos:
        game = sorted(set(int(x) for x in g if x is not None))
        for i in range(len(game)):
            for j in range(i + 1, len(game)):
                covered.add((game[i], game[j]))
    return max(0.0, min(1.0, len(covered) / float(max(1, total_pairs))))


def classify_structural_stagnation(jogos: List[List[int]]) -> Dict[str, float | bool]:
    entropia = calcular_entropia_estrutural(jogos)
    clone = calcular_clone_ratio(jogos)
    cobertura = cobertura_pares(jogos)
    stagnation = (entropia < 0.35) or (clone > 0.75) or (cobertura < 0.25)
    return {
        "entropia": float(entropia),
        "clone_ratio": float(clone),
        "cobertura_pares": float(cobertura),
        "structural_stagnation": bool(stagnation),
    }
