from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class FechamentoSpec:
    code: str
    name: str
    total_numbers: int
    game_size: int
    games_count: int
    fixed_required_count: int
    guarantee_points: int
    description: str


@dataclass
class FechamentoResult:
    pool: List[int]
    fixed: List[int]
    jogos: List[List[int]]
    jogos_rankeados: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
