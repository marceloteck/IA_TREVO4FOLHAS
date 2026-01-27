from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class FechamentoPosicionalSpec:
    code: str
    name: str
    total_numbers: int
    game_size: int
    games_count: int
    fixed_required_count: int
    guarantee_points_declared: int
    group_distribution: List[int]
    description: str
    condition_text: Optional[str] = None


@dataclass
class FechamentoPosicionalResult:
    pool: List[int]
    fixed: List[int]
    groups: List[List[int]]
    jogos: List[List[int]]
    jogos_rankeados: List[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)
