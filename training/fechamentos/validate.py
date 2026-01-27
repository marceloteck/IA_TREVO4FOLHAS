from __future__ import annotations

from typing import Set

from training.fechamentos.types import FechamentoResult, FechamentoSpec


def validate_fechamento_output(spec: FechamentoSpec, result: FechamentoResult) -> None:
    if len(result.pool) != spec.total_numbers:
        raise ValueError("Pool com tamanho inválido para o fechamento.")

    if len(result.fixed) != spec.fixed_required_count:
        raise ValueError("Quantidade de fixas inválida para o fechamento.")

    if not set(result.fixed).issubset(set(result.pool)):
        raise ValueError("Fixas devem ser subconjunto do pool.")

    if len(result.jogos) != spec.games_count:
        raise ValueError("Quantidade de jogos inválida para o fechamento.")

    seen: Set[tuple[int, ...]] = set()
    for jogo in result.jogos:
        if len(jogo) != spec.game_size:
            raise ValueError("Jogo com tamanho inválido.")
        if len(set(jogo)) != len(jogo):
            raise ValueError("Jogo com dezenas duplicadas.")
        if spec.fixed_required_count and not set(result.fixed).issubset(set(jogo)):
            raise ValueError("Jogo sem todas as fixas obrigatórias.")
        key = tuple(sorted(jogo))
        if key in seen:
            raise ValueError("Jogo duplicado dentro do fechamento.")
        seen.add(key)
