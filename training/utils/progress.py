from __future__ import annotations

import faulthandler
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict


def now_ts() -> str:
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def file_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


class ProgressPrinter:
    def __init__(self, progress_every_steps: int = 10, heartbeat_seconds: int = 15, profile_steps: bool = False, stream: Any = sys.stdout):
        self.progress_every_steps = max(1, int(progress_every_steps))
        self.heartbeat_seconds = max(1, int(heartbeat_seconds))
        self.profile_steps = bool(profile_steps)
        self.stream = stream
        self.lock = threading.Lock()
        self.last_log_time = time.time()
        self.state: Dict[str, Any] = {
            "step": None,
            "concurso": None,
            "phase": "idle",
            "mode": None,
            "regime": None,
            "arm": None,
            "recipe": None,
        }

    def set_state(self, **kwargs: Any) -> None:
        with self.lock:
            for key, value in kwargs.items():
                if key in self.state and value is not None:
                    self.state[key] = value

    def log(self, msg: str, update_last_log: bool = True) -> None:
        with self.lock:
            print(f"{now_ts()} {msg}", file=self.stream, flush=True)
            if update_last_log:
                self.last_log_time = time.time()

    def log_step(self, data: Dict[str, Any]) -> None:
        msg = " | ".join(
            [
                f"step={data.get('step')}",
                f"N={data.get('N_from')}->{data.get('N_to')}",
                f"regime={data.get('regime', 'neutro')}",
                f"mode={data.get('mode', 'production')}",
                f"arm={data.get('arm', '-')}",
                f"recipe={data.get('recipe', '-')}",
                f"reward={float(data.get('reward', 0.0)):.2f}",
                f"hit_max={int(data.get('hit_max', 0))}",
                f"14+={int(data.get('total_14p', 0))}",
                f"15={int(data.get('total_15', 0))}",
                f"best_arm={data.get('best_arm', '-')}",
                f"best_recipe={data.get('best_recipe', '-')}",
                f"step_s={float(data.get('elapsed_step_s', 0.0)):.2f}",
            ]
        )
        self.log(msg)

    def log_phases(self, phases_dict: Dict[str, float]) -> None:
        if not self.profile_steps:
            return
        keys = ["features", "generate_candidates", "build_portfolio", "evaluate_hits", "train_meta", "checkpoint", "db_commit", "total"]
        compact = []
        for key in keys:
            if key in phases_dict:
                compact.append(f"{key}={float(phases_dict[key]):.2f}s")
        self.log("phases: " + " ".join(compact))

    def force_flush(self) -> None:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass


class StepTimer:
    def __init__(self) -> None:
        self._step_start = 0.0
        self._last_mark = 0.0
        self._phases: Dict[str, float] = {}

    def start_step(self) -> None:
        now = time.perf_counter()
        self._step_start = now
        self._last_mark = now
        self._phases = {}

    def mark(self, phase_name: str) -> None:
        now = time.perf_counter()
        if self._last_mark > 0.0:
            self._phases[str(phase_name)] = now - self._last_mark
        self._last_mark = now

    def end_step(self) -> Dict[str, float]:
        now = time.perf_counter()
        total = now - self._step_start if self._step_start > 0 else 0.0
        out = dict(self._phases)
        out["total"] = total
        return out


class Heartbeat(threading.Thread):
    def __init__(self, printer: ProgressPrinter, seconds: int = 15, freeze_warn_seconds: int = 60):
        super().__init__(daemon=True)
        self.printer = printer
        self.seconds = max(1, int(seconds))
        self.freeze_warn_seconds = max(self.seconds, int(freeze_warn_seconds))
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(self.seconds):
            now = time.time()
            with self.printer.lock:
                state = dict(self.printer.state)
                since_last = now - self.printer.last_log_time
            self.printer.log(
                f"⏳ rodando... step={state.get('step')} N={state.get('concurso')} "
                f"phase={state.get('phase')} mode={state.get('mode')} since_last_log={since_last:.1f}s",
                update_last_log=False,
            )
            if since_last >= float(self.freeze_warn_seconds):
                self.printer.log("⚠️ watchdog: sem logs recentes; dump leve da stack principal")
                try:
                    faulthandler.dump_traceback(file=sys.stdout)
                except Exception:
                    pass
                self.printer.force_flush()
