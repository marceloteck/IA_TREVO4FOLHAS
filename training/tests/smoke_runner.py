from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "training.backtest.backtest_smart_engine",
        "--steps",
        "30",
        "--panel",
        "0",
        "--progress-every",
        "10",
        "--summary-every",
        "0",
        "--heartbeat-seconds",
        "5",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")

    checks = {
        "watchdog_dump_absent": "dump leve da stack principal" not in out,
        "evaluate_hits_seen": "phase=evaluate_hits" in out,
        "baseline_msg_seen": "Baseline real calculado via DB" in out or "baseline_db: poucos dados" in out,
        "mlp_batch_clamp_seen": "mlp: batch_size ajustado" in out,
    }
    for k, ok in checks.items():
        print(f"{k}={ok}")
    return 0 if proc.returncode == 0 and all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
