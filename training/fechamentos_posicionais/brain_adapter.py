from __future__ import annotations

from typing import Any, List

from training.core.brain_hub import BrainHub
from training.backtest.backtest_engine import register_brains_auto


def build_brain_hub(conn, **kwargs: Any) -> BrainHub:
    return BrainHub(conn, **kwargs)


def register_all_brains(conn, hub: BrainHub) -> List[str]:
    return register_brains_auto(conn, hub)
