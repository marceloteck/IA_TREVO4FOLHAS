from __future__ import annotations

from training.meta.diversity import portfolio_diversity


def compute_hits_distribution(games: list[list[int]], result: list[int]) -> dict:
    r = set(int(x) for x in result)
    dist = {"12": 0, "13": 0, "14": 0, "15": 0}
    for g in games:
        h = len(set(int(x) for x in g) & r)
        if h >= 12:
            k = str(min(15, h))
            if k in dist:
                dist[k] += 1
    return dist


def compute_hit_max(hits_dist: dict) -> int:
    for k in ("15", "14", "13", "12"):
        if int(hits_dist.get(k, 0)) > 0:
            return int(k)
    return 11


def compute_portfolio_diversity(games: list[list[int]]) -> float:
    return float(portfolio_diversity(games))


def compute_score_summary(hits_dist: dict, diversity: float) -> dict:
    hit_max = compute_hit_max(hits_dist)
    c15 = int(hits_dist.get("15", 0))
    c14 = int(hits_dist.get("14", 0))
    c13 = int(hits_dist.get("13", 0))
    c12 = int(hits_dist.get("12", 0))
    score_proxy = c15 * 5.0 + c14 * 2.0 + c13 * 0.5 + c12 * 0.2 + float(diversity) * 0.3
    return {
        "hit_max": int(hit_max),
        "count_13": c13,
        "count_12": c12,
        "diversity": float(diversity),
        "score_proxy": float(score_proxy),
    }
