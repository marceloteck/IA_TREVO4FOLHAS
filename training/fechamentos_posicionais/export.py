from __future__ import annotations

from typing import Any, Dict, List

from training.fechamentos_posicionais.types import FechamentoPosicionalResult


def to_json(output: FechamentoPosicionalResult) -> Dict[str, Any]:
    return {
        "pool": list(output.pool),
        "fixed": list(output.fixed),
        "groups": [list(group) for group in output.groups],
        "jogos": [list(jogo) for jogo in output.jogos],
        "jogos_rankeados": output.jogos_rankeados,
        "metadata": output.metadata,
    }


def _format_game_line(idx: int, game: List[int], score: float) -> str:
    dezenas = " ".join(f"{d:02d}" for d in game)
    return f"JOGO {idx}: {dezenas} | score={score:.4f}"


def to_txt(output: FechamentoPosicionalResult) -> str:
    lines: List[str] = []
    spec = output.metadata.get("spec", {}) if isinstance(output.metadata, dict) else {}
    code = spec.get("code", "N/A")
    guarantee = spec.get("guarantee_points_declared", "N/A")

    lines.append(f"FECHAMENTO POSICIONAL: {code}")
    lines.append(f"GARANTIA DECLARADA (modelo): {guarantee} pontos")
    lines.append(
        "Produto estatístico e informativo. Loterias envolvem aleatoriedade. Não existe garantia de prêmio."
    )
    if output.metadata.get("condition_text"):
        lines.append(f"CONDICAO: {output.metadata['condition_text']}")
    lines.append(f"FIXAS: {' '.join(f'{d:02d}' for d in output.fixed) if output.fixed else '-'}")
    lines.append(f"POOL: {' '.join(f'{d:02d}' for d in output.pool)}")
    lines.append(
        "GRUPOS: " + " | ".join(" ".join(f"{d:02d}" for d in group) for group in output.groups)
    )
    lines.append("")

    ranked = output.jogos_rankeados or [{"jogo": jogo, "score": 0.0} for jogo in output.jogos]
    for idx, item in enumerate(ranked, 1):
        jogo = item.get("jogo", [])
        score = float(item.get("score", 0.0))
        lines.append(_format_game_line(idx, jogo, score))
    return "\n".join(lines)
