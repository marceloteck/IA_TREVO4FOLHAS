from __future__ import annotations

import time


class Throttle:
    def __init__(self, cfg: dict):
        th = dict((cfg or {}).get("throttle", {}))
        self.enabled = bool(th.get("enabled", False))
        self.sleep_every_steps = max(1, int(th.get("sleep_every_steps", 25)))
        self.sleep_ms = max(0, int(th.get("sleep_ms", 30)))

    def maybe_sleep(self, step: int):
        if not self.enabled:
            return
        if int(step) % self.sleep_every_steps == 0:
            time.sleep(self.sleep_ms / 1000.0)
