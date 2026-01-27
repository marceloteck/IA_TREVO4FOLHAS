from __future__ import annotations

from typing import Any, Dict, List

from training.fechamentos.types import FechamentoResult


def to_json(output: FechamentoResult) -> Dict[str, Any]:
    return {
        "pool": list(output.pool),
        "fixed": list(output.fixed),
        "jogos": [list(jogo) for jogo in output.jogos],
        "jogos_rankeados": output.jogos_rankeados,
        "metadata": output.metadata,
    }


def _format_game_line(idx: int, game: List[int], score: float) -> str:
    dezenas = " ".join(f"{d:02d}" for d in game)
    return f"JOGO {idx}: {dezenas} | score={score:.4f}"


def to_txt(output: FechamentoResult) -> str:
    lines: List[str] = []
    spec = output.metadata.get("spec", {}) if isinstance(output.metadata, dict) else {}
    code = spec.get("code", "N/A")
    guarantee = spec.get("guarantee_points", "N/A")
    fixed = output.fixed
    pool = output.pool

    lines.append(f"FECHAMENTO: {code}")
    lines.append(f"GARANTIA DECLARADA (modelo): {guarantee} pontos")
    lines.append(f"FIXAS: {' '.join(f'{d:02d}' for d in fixed) if fixed else '-'}")
    lines.append(f"POOL: {' '.join(f'{d:02d}' for d in pool)}")
    lines.append("")

    ranked = output.jogos_rankeados or [{"jogo": jogo, "score": 0.0} for jogo in output.jogos]
    for idx, item in enumerate(ranked, 1):
        jogo = item.get("jogo", [])
        score = float(item.get("score", 0.0))
        lines.append(_format_game_line(idx, jogo, score))
    return "\n".join(lines)
