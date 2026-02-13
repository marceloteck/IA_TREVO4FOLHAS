from __future__ import annotations


class ModeManager:
    def __init__(self, cfg: dict):
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        self.cooldown_steps = max(1, int(self.cfg.get("cooldown_steps", 30)))
        self.mode = "production"
        self.last_switch_step = 0
        self.stable_counter = 0
        self.bad_perf_counter = 0

    def decide_mode(self, regime_id: int, stagnation: dict, recent_perf: dict) -> str:
        if not self.enabled:
            return "production"

        step = int(recent_perf.get("step", 0))
        can_switch = (step - self.last_switch_step) >= self.cooldown_steps

        rescue_mode = bool(stagnation.get("rescue_mode", False))
        bad_perf = bool(recent_perf.get("is_bad", False))
        stable = bool(recent_perf.get("is_stable", False))

        if stable and not rescue_mode and regime_id != 3:
            self.stable_counter += 1
        else:
            self.stable_counter = 0

        if bad_perf:
            self.bad_perf_counter += 1
        else:
            self.bad_perf_counter = max(0, self.bad_perf_counter - 1)

        sw_research = self.cfg.get("switch_to_research", {})
        sw_production = self.cfg.get("switch_to_production", {})

        to_research = (
            (bool(sw_research.get("on_instable_regime", True)) and int(regime_id) == 3)
            or (bool(sw_research.get("on_rescue_mode", True)) and rescue_mode)
            or (self.bad_perf_counter >= int(sw_research.get("bad_perf_steps", 50)))
        )
        to_production = self.stable_counter >= int(sw_production.get("stable_steps", 60))

        if can_switch:
            if self.mode == "production" and to_research:
                self.mode = "research"
                self.last_switch_step = step
            elif self.mode == "research" and to_production:
                self.mode = "production"
                self.last_switch_step = step

        return self.mode


    def get_state(self) -> dict:
        return {
            "mode": self.mode,
            "last_switch_step": int(self.last_switch_step),
            "stable_counter": int(self.stable_counter),
            "bad_perf_counter": int(self.bad_perf_counter),
        }

    def set_state(self, state: dict) -> None:
        self.mode = str(state.get("mode", self.mode))
        self.last_switch_step = int(state.get("last_switch_step", self.last_switch_step))
        self.stable_counter = int(state.get("stable_counter", self.stable_counter))
        self.bad_perf_counter = int(state.get("bad_perf_counter", self.bad_perf_counter))
