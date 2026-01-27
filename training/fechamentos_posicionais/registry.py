from __future__ import annotations

from typing import List

from training.fechamentos_posicionais.specs import SPEC_BY_CODE, SPECS
from training.fechamentos_posicionais.types import FechamentoPosicionalSpec


def _validate_spec(spec: FechamentoPosicionalSpec) -> None:
    if spec.total_numbers <= 0:
        raise ValueError(f"Spec inválido ({spec.code}): total_numbers <= 0")
    if spec.game_size <= 0:
        raise ValueError(f"Spec inválido ({spec.code}): game_size <= 0")
    if spec.games_count <= 0:
        raise ValueError(f"Spec inválido ({spec.code}): games_count <= 0")
    if spec.fixed_required_count < 0:
        raise ValueError(f"Spec inválido ({spec.code}): fixed_required_count < 0")
    if spec.fixed_required_count > spec.total_numbers:
        raise ValueError(f"Spec inválido ({spec.code}): fixed_required_count > total_numbers")
    if spec.game_size > spec.total_numbers:
        raise ValueError(f"Spec inválido ({spec.code}): game_size > total_numbers")
    if not spec.group_distribution:
        raise ValueError(f"Spec inválido ({spec.code}): group_distribution vazio")


def list_specs() -> List[FechamentoPosicionalSpec]:
    for spec in SPECS:
        _validate_spec(spec)
    return list(SPECS)


def get_spec(code: str) -> FechamentoPosicionalSpec:
    code_norm = code.strip().upper()
    if code_norm not in SPEC_BY_CODE:
        raise KeyError(f"Fechamento posicional '{code}' não registrado.")
    return SPEC_BY_CODE[code_norm]
