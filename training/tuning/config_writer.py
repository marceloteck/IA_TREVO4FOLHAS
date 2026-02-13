from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_update_json(path: str, updates: dict, backup: bool = True) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    base = {}
    if p.exists():
        base = json.loads(p.read_text(encoding="utf-8"))
    if backup and p.exists():
        bak = p.with_suffix(p.suffix + f".bak_{now_tag()}")
        bak.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

    def _deep_set(d: dict, u: dict):
        for k, v in u.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                _deep_set(d[k], v)
            else:
                d[k] = v

    _deep_set(base, dict(updates or {}))
    p.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
