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
from training.fechamentos.auto_select import AutoSelectConfig, pick_pool_and_fixed
from training.fechamentos.generator import generate_fechamento
from training.fechamentos.registry import list_specs


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


@pytest.mark.parametrize("spec", list_specs())
def test_fechamentos_auto_specs(spec):
    hub = _build_hub()
    rng = random.Random(123)
    context: Dict[str, Any] = {}
    auto_config = AutoSelectConfig(candidate_pools=30, pool_samples=8, max_random_swaps=4)

    pool, fixed, meta = pick_pool_and_fixed(spec, hub, context, rng, auto_config)
    result = generate_fechamento(
        spec,
        pool,
        fixed,
        hub,
        context=context,
        rng=rng,
        max_candidates=2000,
        selection_metadata=meta,
    )

    assert len(result.pool) == spec.total_numbers
    assert len(result.fixed) == spec.fixed_required_count
    assert len(result.jogos) == spec.games_count
    for jogo in result.jogos:
        assert len(jogo) == spec.game_size
        if spec.fixed_required_count:
            assert set(result.fixed).issubset(set(jogo))


def test_fechamentos_auto_performance_focus():
    hub = _build_hub()
    rng = random.Random(321)
    context: Dict[str, Any] = {}
    specs = [spec for spec in list_specs() if spec.code in {"FC44", "FC3"}]

    for spec in specs:
        pool, fixed, meta = pick_pool_and_fixed(
            spec,
            hub,
            context,
            rng,
            AutoSelectConfig(candidate_pools=20, pool_samples=6, max_random_swaps=3),
        )
        result = generate_fechamento(
            spec,
            pool,
            fixed,
            hub,
            context=context,
            rng=rng,
            max_candidates=1500,
            selection_metadata=meta,
        )
        assert len(result.jogos) == spec.games_count
