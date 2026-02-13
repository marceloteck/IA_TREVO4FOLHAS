from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


def compute_config_hash(config_dir: str) -> str:
    root = Path(config_dir)
    blobs: list[str] = []
    for p in sorted(root.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            norm = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            norm = p.read_text(encoding="utf-8", errors="ignore")
        blobs.append(f"{p.name}:{norm}")
    payload = "\n".join(blobs)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def try_get_git_commit() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode("utf-8").strip() or "unknown"
    except Exception:
        return "unknown"
