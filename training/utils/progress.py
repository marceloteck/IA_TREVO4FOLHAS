from __future__ import annotations

import faulthandler
import os
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
    def __init__(
        self,
        progress_every_steps: int = 10,
        heartbeat_seconds: int = 15,
        profile_steps: bool = False,
        stream: Any = sys.stdout,
        progress_log_every_s: float = 15.0,
        watchdog_dump_cooldown_s: float = 120.0,
    ):
        self.progress_every_steps = max(1, int(progress_every_steps))
        self.heartbeat_seconds = max(1, int(heartbeat_seconds))
        self.profile_steps = bool(profile_steps)
        self.stream = stream
        self.lock = threading.Lock()
        now = time.time()
        self.last_log_time = now
        self.last_heartbeat_time = 0.0
        self.last_heartbeat_log_time = 0.0
        self.progress_log_every_s = max(1.0, float(progress_log_every_s))
        self.watchdog_dump_cooldown_s = max(5.0, float(watchdog_dump_cooldown_s))
        self._last_dump_ts = 0.0
        self.heartbeat_snapshot: Dict[str, Any] = {}
        self._phase_last_log: Dict[str, float] = {}
        self.state: Dict[str, Any] = {
            "step": None,
            "concurso": None,
            "phase": "idle",
            "detail": None,
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

    def set_phase(self, phase: str, detail: str | None = None) -> None:
        payload: Dict[str, Any] = {"phase": str(phase)}
        if detail is not None:
            payload["detail"] = str(detail)
        self.set_state(**payload)

    def set_progress_log_every(self, seconds: float) -> None:
        with self.lock:
            self.progress_log_every_s = max(1.0, float(seconds))

    def set_watchdog_dump_cooldown(self, seconds: float) -> None:
        with self.lock:
            self.watchdog_dump_cooldown_s = max(5.0, float(seconds))

    def log(self, msg: str, update_last_log: bool = True) -> None:
        with self.lock:
            print(f"{now_ts()} {msg}", file=self.stream, flush=True)
            if update_last_log:
                self.last_log_time = time.time()

    def touch_activity(self, payload: Dict[str, Any] | None = None) -> None:
        with self.lock:
            now = time.time()
            self.last_heartbeat_time = now
            if isinstance(payload, dict) and payload:
                self.heartbeat_snapshot = dict(payload)

    def heartbeat(self, payload: Dict[str, Any] | None = None, log_every_s: float | None = None) -> None:
        data = dict(payload or {})
        self.touch_activity(data)

        phase = str(data.get("phase", "") or "")
        if phase:
            self.set_phase(phase, detail=str(data.get("subphase") or data.get("detail") or "") or None)
        elif (data.get("subphase") or data.get("detail")) and str(self.state.get("phase")):
            self.set_phase(str(self.state.get("phase")), detail=str(data.get("subphase") or data.get("detail")))

        every = max(1.0, float(log_every_s) if log_every_s is not None else float(self.progress_log_every_s))
        should_log = False
        with self.lock:
            now = time.time()
            if (now - float(self.last_heartbeat_log_time)) >= every:
                self.last_heartbeat_log_time = now
                should_log = True
        if should_log:
            sub = str(data.get("subphase") or data.get("detail") or self.state.get("detail") or "-")
            i = int(data.get("i", 0))
            n = int(data.get("n", 0))
            elapsed = float(data.get("elapsed", 0.0))
            rate = float(data.get("rate", 0.0))
            extra_rate = f" rate={rate:.1f}/s" if rate > 0 else ""
            if n > 0:
                self.log(f"💓 activity phase={self.state.get('phase')} detail={sub} i={i}/{n} elapsed={elapsed:.1f}s{extra_rate}")
            else:
                last_ok = int(data.get("last_ok", 0))
                last_fail = int(data.get("last_fail", 0))
                self.log(
                    f"💓 activity phase={self.state.get('phase')} detail={sub} elapsed={elapsed:.1f}s"
                    f" last_ok={last_ok} last_fail={last_fail}{extra_rate}"
                )

    def tick(self, phase: str, detail: str | None = None, i: int | None = None, total: int | None = None) -> None:
        payload: Dict[str, Any] = {"phase": str(phase)}
        if detail is not None:
            payload["detail"] = str(detail)
        if i is not None:
            payload["i"] = int(i)
        if total is not None:
            payload["n"] = int(total)
        self.heartbeat(payload, log_every_s=self.progress_log_every_s)

    def log_every(self, phase: str, seconds: float, message: str) -> None:
        now = time.time()
        phase_key = str(phase)
        with self.lock:
            last = float(self._phase_last_log.get(phase_key, 0.0))
            if (now - last) < max(1.0, float(seconds)):
                return
            self._phase_last_log[phase_key] = now
        self.log(message)

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
        env_watchdog = os.getenv("IA_WATCHDOG_SECONDS", "").strip()
        if env_watchdog:
            try:
                freeze_warn_seconds = int(float(env_watchdog))
            except Exception:
                pass
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
                since_heartbeat = (now - self.printer.last_heartbeat_time) if self.printer.last_heartbeat_time > 0 else float("inf")
                hb_data = dict(self.printer.heartbeat_snapshot)
            detail = state.get("detail") or "-"
            self.printer.log(
                f"⏳ rodando... step={state.get('step')} N={state.get('concurso')} "
                f"phase={state.get('phase')} detail={detail} mode={state.get('mode')} since_last_log={since_last:.1f}s",
                update_last_log=False,
            )
            heavy_phase = str(state.get("phase", "")) in {"evaluate_hits", "features", "generate_candidates"}
            if since_heartbeat >= float(self.freeze_warn_seconds):
                now_dump = time.time()
                with self.printer.lock:
                    cooldown = float(self.printer.watchdog_dump_cooldown_s)
                    can_dump = (now_dump - float(self.printer._last_dump_ts)) >= cooldown
                    if can_dump:
                        self.printer._last_dump_ts = now_dump
                if not can_dump:
                    self.printer.log("ℹ️ watchdog: cooldown ativo; dump já emitido recentemente")
                    continue
                self.printer.log(
                    "⚠️ watchdog: sem logs recentes (pode ser etapa longa, não necessariamente erro); "
                    f"state phase={state.get('phase')} detail={detail} i={hb_data.get('i', '-')}/{hb_data.get('n', '-')} elapsed={float(hb_data.get('elapsed', 0.0)):.1f}s; "
                    "dump leve da stack principal"
                )
                try:
                    faulthandler.dump_traceback(file=sys.stdout)
                except Exception:
                    pass
                self.printer.force_flush()
