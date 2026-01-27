from __future__ import annotations

import random
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.core.brain_hub import BrainHub
from training.core.brain_interface import BrainInterface
from training.fechamentos_posicionais.auto_select import AutoSelectConfig, pick_pool_and_fixed
from training.fechamentos_posicionais.generator import generate_fechamento
from training.fechamentos_posicionais.grouping import plan_groups
from training.fechamentos_posicionais.registry import get_spec


class DummyBrain(BrainInterface):
    id = "dummy"
    name = "Dummy"
    category = "test"
    version = "0.1"

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        return 1.0

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        base = list(range(1, 26))
        games = []
        for i in range(n):
            start = i % (25 - size + 1)
            games.append(sorted(base[start : start + size]))
        return games

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        return float(sum(jogo))

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        return None

    def save_state(self) -> None:
        return None

    def load_state(self) -> None:
        return None

    def report(self) -> Dict[str, Any]:
        return {}


def _build_hub() -> BrainHub:
    conn = sqlite3.connect(":memory:")
    hub = BrainHub(conn)
    hub.register(DummyBrain())
    return hub


@pytest.mark.parametrize("code", ["FC93", "FC94", "FC85", "FC128"])
def test_posicional_basic_flow(code):
    hub = _build_hub()
    rng = random.Random(123)
    context: Dict[str, Any] = {}

    spec = get_spec(code)
    pool, fixed, meta = pick_pool_and_fixed(spec, hub, context, rng, AutoSelectConfig(candidate_pools=20, pool_samples=6))
    group_plan = plan_groups(spec, pool, fixed, hub, context, rng)
    result = generate_fechamento(
        spec,
        pool,
        fixed,
        group_plan.groups,
        hub,
        context=context,
        rng=rng,
        selection_metadata={**meta, **{"groups": group_plan.metadata}},
    )

    assert len(result.pool) == spec.total_numbers
    assert len(result.fixed) == spec.fixed_required_count
    assert len(result.jogos) == spec.games_count
    assert sum(len(g) for g in result.groups) == spec.total_numbers - spec.fixed_required_count
    for jogo in result.jogos:
        assert len(jogo) == spec.game_size
        if spec.fixed_required_count:
            assert set(result.fixed).issubset(set(jogo))
