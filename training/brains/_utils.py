# training/brains/_utils.py
from __future__ import annotations

import hashlib
import heapq
import json
import math
import random
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List

UNIVERSO = list(range(1, 26))

_DEFAULT_PERF = {
    "safe_sampling_fallback": True,
    "weighted_sample_max_s": 10.0,
    "heartbeat_every_s": 0.5,
    "progress_log_every_s": 15.0,
    "weighted_sample_perf_log_ms": 200.0,
}

_RUNTIME_CFG: Dict[str, Any] = {
    "heartbeat_cb": None,
    "heartbeat_every_s": None,
    "safe_sampling_fallback": None,
    "weighted_sample_max_s": None,
}

_PERF_CACHE: Dict[str, Any] = {"loaded": False, "data": dict(_DEFAULT_PERF)}
_NORM_CACHE: "OrderedDict[str, tuple[List[int], List[float], float]]" = OrderedDict()
_NORM_CACHE_MAX = 64


def _load_performance_cfg() -> Dict[str, Any]:
    if bool(_PERF_CACHE.get("loaded", False)):
        return dict(_PERF_CACHE.get("data", _DEFAULT_PERF))
    out = dict(_DEFAULT_PERF)
    try:
        root = Path(__file__).resolve().parents[2]
        path = root / "config" / "performance.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.update(data)
    except Exception:
        pass
    _PERF_CACHE["loaded"] = True
    _PERF_CACHE["data"] = dict(out)
    return out


def configure_weighted_sampling_runtime(
    heartbeat_cb: Callable[[Dict[str, Any]], None] | None = None,
    heartbeat_every_s: float | None = None,
    safe_sampling_fallback: bool | None = None,
    weighted_sample_max_s: float | None = None,
) -> None:
    _RUNTIME_CFG["heartbeat_cb"] = heartbeat_cb if callable(heartbeat_cb) else None
    _RUNTIME_CFG["heartbeat_every_s"] = heartbeat_every_s
    _RUNTIME_CFG["safe_sampling_fallback"] = safe_sampling_fallback
    _RUNTIME_CFG["weighted_sample_max_s"] = weighted_sample_max_s


def _cache_key(weights: Dict[int, float]) -> str:
    parts = [f"{int(k)}:{float(v):.8f}" for k, v in sorted(weights.items(), key=lambda x: int(x[0]))]
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def _normalized_from_weights(weights: Dict[int, float]) -> tuple[List[int], List[float], float]:
    key = _cache_key(weights)
    cached = _NORM_CACHE.get(key)
    if cached is not None:
        _NORM_CACHE.move_to_end(key)
        return list(cached[0]), list(cached[1]), float(cached[2])

    pool: List[int] = []
    w: List[float] = []
    for k, v in sorted(weights.items(), key=lambda x: int(x[0])):
        pool.append(int(k))
        w.append(max(0.0, float(v)))
    total = float(sum(w))
    if total <= 0.0 and pool:
        w = [1.0 for _ in pool]
        total = float(len(pool))

    _NORM_CACHE[key] = (list(pool), list(w), float(total))
    _NORM_CACHE.move_to_end(key)
    if len(_NORM_CACHE) > _NORM_CACHE_MAX:
        _NORM_CACHE.popitem(last=False)
    return pool, w, total


def _fallback_weighted_sample(pool: List[int], w: List[float], remaining: int, rng: random.Random | None = None) -> List[int]:
    remaining = max(0, min(int(remaining), len(pool)))
    if remaining <= 0:
        return []

    rr = rng if isinstance(rng, random.Random) else random
    try:
        import numpy as np

        arr = np.array([max(0.0, float(x)) for x in w], dtype=float)
        total = float(arr.sum())
        if total <= 0.0:
            idx = np.random.choice(len(pool), size=remaining, replace=False)
            return [int(pool[int(i)]) for i in idx.tolist()]
        probs = arr / total
        idx = np.random.choice(len(pool), size=remaining, replace=False, p=probs)
        return [int(pool[int(i)]) for i in idx.tolist()]
    except Exception:
        pass

    positives: List[tuple[int, float]] = []
    zeros: List[int] = []
    for i, item in enumerate(pool):
        wi = max(0.0, float(w[i]))
        if wi > 0.0:
            positives.append((int(item), wi))
        else:
            zeros.append(int(item))

    if not positives:
        rr.shuffle(zeros)
        return zeros[:remaining]

    # Efraimidis–Spirakis (A-Res) com heap mínimo (O(n log k)).
    k_eff = min(remaining, len(positives))
    heap: List[tuple[float, int]] = []
    for item, wi in positives:
        u = max(1e-12, rr.random())
        key = math.log(u) / wi
        if len(heap) < k_eff:
            heapq.heappush(heap, (key, int(item)))
        elif key > heap[0][0]:
            heapq.heapreplace(heap, (key, int(item)))

    out = [int(x[1]) for x in heap]
    if len(out) < remaining and zeros:
        rr.shuffle(zeros)
        out.extend(zeros[: remaining - len(out)])
    return out


def weighted_sample_without_replacement(
    weights: Dict[int, float],
    k: int,
    heartbeat_cb: Callable[[Dict[str, Any]], None] | None = None,
    heartbeat_every: float | None = None,
    rng: random.Random | None = None,
) -> List[int]:
    pool, w, total = _normalized_from_weights(weights)
    if k <= 0 or not pool:
        return []

    perf = _load_performance_cfg()
    hb_cb = heartbeat_cb if callable(heartbeat_cb) else _RUNTIME_CFG.get("heartbeat_cb")
    hb_every = float(
        heartbeat_every
        if heartbeat_every is not None
        else (_RUNTIME_CFG.get("heartbeat_every_s") if _RUNTIME_CFG.get("heartbeat_every_s") is not None else perf.get("heartbeat_every_s", 0.5))
    )
    hb_every = max(0.05, hb_every)

    safe_fallback = _RUNTIME_CFG.get("safe_sampling_fallback")
    if safe_fallback is None:
        safe_fallback = bool(perf.get("safe_sampling_fallback", True))
    max_s = _RUNTIME_CFG.get("weighted_sample_max_s")
    if max_s is None:
        max_s = float(perf.get("weighted_sample_max_s", 10.0))
    max_s = max(0.05, float(max_s))

    k = min(int(k), len(pool))
    started = time.perf_counter()
    last_hb = started

    # caminho rápido com numpy
    if bool(safe_fallback):
        try:
            import numpy as np

            arr = np.array(pool, dtype=int)
            ww = np.array([max(0.0, float(x)) for x in w], dtype=float)
            if float(ww.sum()) <= 0.0:
                idx = np.random.choice(len(arr), size=k, replace=False)
            else:
                probs = ww / float(ww.sum())
                idx = np.random.choice(len(arr), size=k, replace=False, p=probs)
            result_fast = sorted(int(arr[int(i)]) for i in idx.tolist())
            dt_ms = (time.perf_counter() - started) * 1000.0
            if dt_ms > float(perf.get("weighted_sample_perf_log_ms", 200.0)):
                print(f"perf: weighted_sample_without_replacement took {dt_ms:.1f}ms n={len(pool)} k={k}", flush=True)
            return result_fast
        except Exception:
            pass

    result = _fallback_weighted_sample(pool, w, k, rng=rng)

    now = time.perf_counter()
    elapsed = now - started
    if callable(hb_cb) and (now - last_hb) >= hb_every:
        try:
            hb_cb(
                {
                    "phase": "generate_candidates",
                    "subphase": "weighted_sample",
                    "i": int(k),
                    "n": int(k),
                    "elapsed": float(elapsed),
                }
            )
        except Exception:
            pass

    if elapsed >= max_s and bool(safe_fallback):
        print(
            f"[weighted_sample] ⚠️ guardrail ativo após {elapsed:.2f}s; fallback seguro aplicado (n={len(pool)} k={k})",
            flush=True,
        )

    dt_ms = elapsed * 1000.0
    if dt_ms > float(perf.get("weighted_sample_perf_log_ms", 200.0)):
        print(f"perf: weighted_sample_without_replacement took {dt_ms:.1f}ms n={len(pool)} k={k}", flush=True)

    return sorted(int(x) for x in result)


def count_even(jogo: List[int]) -> int:
    return sum(1 for x in jogo if x % 2 == 0)


def max_consecutive_run(jogo: List[int]) -> int:
    s = sorted(jogo)
    best = cur = 1
    for i in range(1, len(s)):
        if s[i] == s[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best
