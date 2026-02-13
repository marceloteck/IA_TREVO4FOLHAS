from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import joblib


DEFAULT_MODEL_PATH = Path("data/models/meta_controller.pkl")


class ModelStore:
    def __init__(self, path: Path | str = DEFAULT_MODEL_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, payload: Dict[str, Any]) -> None:
        joblib.dump(payload, self.path)

    def load(self) -> Dict[str, Any] | None:
        if not self.path.exists():
            return None
        return joblib.load(self.path)

    def save_state(self, state: Dict[str, Any]) -> str:
        self.save(state)
        return str(self.path)

    def load_state(self) -> Dict[str, Any] | None:
        return self.load()
