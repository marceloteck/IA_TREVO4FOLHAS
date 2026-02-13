from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Dict, List


FEATURE_NAMES = [
    "mean_even_120",
    "mean_even_300",
    "mean_sum_120",
    "mean_sum_300",
    "mean_repeat_120",
    "std_sum_120",
    "entropy_freq_120",
    "drift_freq_120",
    "hot_share_120",
    "cold_share_120",
    "avg_delay_120",
    "max_delay_120",
    "last_arm_id",
    "last_recipe_id",
    "recipe_age",
    "arm_recent_reward",
    "recipe_recent_reward",
    "stagnation_score",
    "exploration_rate_current",
    "regime_id",
]


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _stable_id(value: str) -> float:
    if not value:
        return 0.0
    h = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / float(0xFFFFFFFF)


def _fetch_recent_rows(conn: sqlite3.Connection, concurso_atual: int, limit: int) -> List[List[int]]:
    rows = conn.execute(
        """
        SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        WHERE concurso <= ?
        ORDER BY concurso DESC
        LIMIT ?
        """,
        (int(concurso_atual), int(limit)),
    ).fetchall()
    return [[int(x) for x in row] for row in reversed(rows)]


def _history_stats(history: List[List[int]]) -> Dict[str, float]:
    if not history:
        return {
            "mean_even": 0.0,
            "mean_sum": 0.0,
            "mean_repeat": 0.0,
            "std_sum": 0.0,
            "entropy": 0.0,
            "drift": 0.0,
            "hot_share": 0.0,
            "cold_share": 0.0,
            "avg_delay": 1.0,
            "max_delay": 1.0,
        }

    sums = [sum(r) for r in history]
    even_ratio = [sum(1 for d in r if d % 2 == 0) / 15.0 for r in history]

    repeats = []
    for i in range(1, len(history)):
        repeats.append(len(set(history[i]) & set(history[i - 1])) / 15.0)

    freq = {i: 0 for i in range(1, 26)}
    for r in history:
        for d in r:
            freq[d] += 1

    total_marks = max(1, len(history) * 15)
    probs = [freq[i] / float(total_marks) for i in range(1, 26)]
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    entropy_norm = entropy / math.log2(25)

    half = max(1, len(history) // 2)
    freq_a = {i: 0 for i in range(1, 26)}
    freq_b = {i: 0 for i in range(1, 26)}
    for r in history[:half]:
        for d in r:
            freq_a[d] += 1
    for r in history[half:]:
        for d in r:
            freq_b[d] += 1
    norm_a = max(1, half * 15)
    norm_b = max(1, (len(history) - half) * 15)
    drift = sum(abs((freq_a[i] / norm_a) - (freq_b[i] / norm_b)) for i in range(1, 26)) / 2.0

    ranked = sorted(range(1, 26), key=lambda d: freq[d], reverse=True)
    hot = set(ranked[:5])
    cold = set(ranked[-5:])
    hot_share = sum(freq[d] for d in hot) / float(total_marks)
    cold_share = sum(freq[d] for d in cold) / float(total_marks)

    delays = []
    for d in range(1, 26):
        delay = len(history)
        for idx in range(len(history) - 1, -1, -1):
            if d in history[idx]:
                delay = len(history) - 1 - idx
                break
        delays.append(delay / float(max(1, len(history))))

    mean_sum_norm = (sum(sums) / len(sums) - 120.0) / 150.0
    std_sum_norm = (math.sqrt(sum((s - (sum(sums) / len(sums))) ** 2 for s in sums) / len(sums))) / 50.0

    return {
        "mean_even": _clamp01(sum(even_ratio) / len(even_ratio)),
        "mean_sum": _clamp01(mean_sum_norm),
        "mean_repeat": _clamp01((sum(repeats) / max(1, len(repeats))) if repeats else 0.0),
        "std_sum": _clamp01(std_sum_norm),
        "entropy": _clamp01(entropy_norm),
        "drift": _clamp01(drift),
        "hot_share": _clamp01(hot_share),
        "cold_share": _clamp01(cold_share),
        "avg_delay": _clamp01(sum(delays) / len(delays)),
        "max_delay": _clamp01(max(delays)),
    }


def extract_context_features(
    db_conn: sqlite3.Connection,
    concurso_atual: int,
    janela_120: int = 120,
    janela_300: int = 300,
    overrides: dict | None = None,
) -> dict:
    hist_120 = _fetch_recent_rows(db_conn, concurso_atual, int(janela_120))
    hist_300 = _fetch_recent_rows(db_conn, concurso_atual, int(janela_300))
    s120 = _history_stats(hist_120)
    s300 = _history_stats(hist_300)

    last_decision = db_conn.execute(
        """
        SELECT run_id, step, arm, recipe, exploration_rate
        FROM decisions
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    last_arm = str(last_decision[2]) if last_decision else ""
    last_recipe = str(last_decision[3]) if last_decision else ""
    exploration_rate = float(last_decision[4]) if last_decision and last_decision[4] is not None else 0.5

    recipe_age = 0.0
    arm_recent_reward = 0.5
    recipe_recent_reward = 0.5
    stagnation_score = 0.0

    if last_decision:
        run_id, step_ref = int(last_decision[0]), int(last_decision[1])
        row_age = db_conn.execute(
            "SELECT MIN(step) FROM decisions WHERE run_id=? AND recipe=?",
            (run_id, last_recipe),
        ).fetchone()
        if row_age and row_age[0] is not None:
            recipe_age = _clamp01((step_ref - int(row_age[0])) / 200.0)

        arm_reward_row = db_conn.execute(
            """
            SELECT AVG(o.reward)
            FROM outcomes o
            JOIN decisions d ON d.run_id=o.run_id AND d.step=o.step
            WHERE d.arm=?
            ORDER BY o.id DESC
            LIMIT 30
            """,
            (last_arm,),
        ).fetchone()
        recipe_reward_row = db_conn.execute(
            """
            SELECT AVG(o.reward)
            FROM outcomes o
            JOIN decisions d ON d.run_id=o.run_id AND d.step=o.step
            WHERE d.recipe=?
            ORDER BY o.id DESC
            LIMIT 30
            """,
            (last_recipe,),
        ).fetchone()

        arm_recent_reward = _clamp01(((float(arm_reward_row[0]) if arm_reward_row and arm_reward_row[0] is not None else 0.0) + 5.0) / 15.0)
        recipe_recent_reward = _clamp01(((float(recipe_reward_row[0]) if recipe_reward_row and recipe_reward_row[0] is not None else 0.0) + 5.0) / 15.0)

        stagnation_row = db_conn.execute(
            "SELECT AVG(CASE WHEN hit_max < 14 THEN 1.0 ELSE 0.0 END) FROM outcomes ORDER BY id DESC LIMIT 20"
        ).fetchone()
        stagnation_score = _clamp01(float(stagnation_row[0]) if stagnation_row and stagnation_row[0] is not None else 0.0)

    regime_id = 0.5
    if s120["mean_repeat"] >= 0.56 and s120["drift"] <= 0.18:
        regime_id = 0.25
    elif s120["mean_repeat"] <= 0.42 and s120["drift"] >= 0.24:
        regime_id = 0.75
    elif s120["mean_sum"] >= s300["mean_sum"]:
        regime_id = 1.0
    else:
        regime_id = 0.0

    features = {
        "mean_even_120": s120["mean_even"],
        "mean_even_300": s300["mean_even"],
        "mean_sum_120": s120["mean_sum"],
        "mean_sum_300": s300["mean_sum"],
        "mean_repeat_120": s120["mean_repeat"],
        "std_sum_120": s120["std_sum"],
        "entropy_freq_120": s120["entropy"],
        "drift_freq_120": s120["drift"],
        "hot_share_120": s120["hot_share"],
        "cold_share_120": s120["cold_share"],
        "avg_delay_120": s120["avg_delay"],
        "max_delay_120": s120["max_delay"],
        "last_arm_id": _stable_id(last_arm),
        "last_recipe_id": _stable_id(last_recipe),
        "recipe_age": _clamp01(recipe_age),
        "arm_recent_reward": arm_recent_reward,
        "recipe_recent_reward": recipe_recent_reward,
        "stagnation_score": _clamp01(stagnation_score),
        "exploration_rate_current": _clamp01(exploration_rate),
        "regime_id": _clamp01(regime_id),
    }

    if overrides:
        for k, v in overrides.items():
            if k in features and v is not None:
                features[k] = _clamp01(float(v))

    return {k: float(features.get(k, 0.0)) for k in FEATURE_NAMES}
