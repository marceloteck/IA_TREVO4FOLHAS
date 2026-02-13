from __future__ import annotations

import hashlib
import json


def serialize_state(state: dict) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_hash(state_json: str) -> str:
    return hashlib.sha256(state_json.encode("utf-8")).hexdigest()


def validate_state(state_json: str, expected_hash: str) -> bool:
    return compute_hash(state_json) == str(expected_hash)
