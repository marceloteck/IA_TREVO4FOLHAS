from __future__ import annotations

from typing import Set

from training.fechamentos_posicionais.types import FechamentoPosicionalResult, FechamentoPosicionalSpec


def validate_fechamento_output(spec: FechamentoPosicionalSpec, result: FechamentoPosicionalResult) -> None:
    if len(result.pool) != spec.total_numbers:
        raise ValueError("Pool com tamanho inválido para o fechamento posicional.")

    if len(result.fixed) != spec.fixed_required_count:
        raise ValueError("Quantidade de fixas inválida para o fechamento posicional.")

    if not set(result.fixed).issubset(set(result.pool)):
        raise ValueError("Fixas devem ser subconjunto do pool.")

    if len(result.jogos) != spec.games_count:
        raise ValueError("Quantidade de jogos inválida para o fechamento posicional.")

    group_total = sum(len(g) for g in result.groups)
    variaveis = [n for n in result.pool if n not in set(result.fixed)]
    if group_total != len(variaveis):
        raise ValueError("Distribuição de grupos não corresponde às variáveis.")

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
