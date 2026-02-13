from __future__ import annotations

import hashlib
from typing import Dict, List, Tuple


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _quantize_context(meta: dict) -> str:
    regime = int(meta.get("regime_id", 0))
    stag = int(float(meta.get("stagnation_score", 0.0)) * 10)
    div = int(float(meta.get("diversity", 0.0)) * 10)
    return f"r{regime}_s{stag}_d{div}"


def _strategy_signature(meta: dict) -> str:
    arm = str(meta.get("arm", "-"))
    recipe = str(meta.get("recipe", "-"))
    brains = str(meta.get("brains_signature", "-"))
    fechamento = str(meta.get("fechamento_tipo", "DIRETO"))
    pool = str(meta.get("pool_size", "-"))
    return f"{arm}|{recipe}|{brains}|{fechamento}|{pool}"


def score_memory_item(
    dezenas: list[int],
    tipo_jogo: int,
    hit: int,
    meta: dict,
    cfg: dict,
) -> Tuple[float, List[str], Dict[str, str]]:
    flags: List[str] = []

    hit_scores = {15: 0.96, 14: 0.83, 13: 0.66, 12: 0.42}
    score = hit_scores.get(int(hit), 0.20)

    allow_12 = bool(cfg.get("allow_12_in_gold", False))
    if int(hit) < 12:
        flags.append("low_hit")
        score -= 0.25
    elif int(hit) == 12 and not allow_12:
        flags.append("hit12_not_preferred")
        score -= 0.12

    even = sum(1 for d in dezenas if int(d) % 2 == 0)
    soma = sum(int(d) for d in dezenas)
    if even < 5 or even > 11:
        flags.append("struct_even_outlier")
        score -= 0.08
    if soma < 140 or soma > 250:
        flags.append("struct_sum_outlier")
        score -= 0.08

    strategy_count = int(meta.get("strategy_recent_count", 0))
    if strategy_count > int(meta.get("strategy_overfit_threshold", 150)):
        flags.append("overfit_suspect")
        score -= 0.10

    if bool(meta.get("is_clone", False)):
        flags.append("clone")
        score -= 0.20

    if bool(meta.get("validated", False)):
        flags.append("validated")
        score += 0.06

    context_signature = _quantize_context(meta)
    strategy_signature = _strategy_signature(meta)
    diversity_tag = f"e{even}_s{(soma // 10) * 10}"

    raw = f"{context_signature}|{strategy_signature}|{','.join(str(int(x)) for x in sorted(dezenas))}"
    short_hash = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    extra = {
        "context_signature": f"{context_signature}_{short_hash[:4]}",
        "strategy_signature": f"{strategy_signature}_{short_hash[4:8]}",
        "diversity_tag": diversity_tag,
    }

    return _clamp01(score), flags, extra
