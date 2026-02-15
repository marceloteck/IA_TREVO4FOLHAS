from __future__ import annotations

import argparse
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Runner contínuo seguro (paper/research por padrão).")
    parser.add_argument("--safe-default", action="store_true", help="Ativa perfil conservador de execução contínua.")
    parser.add_argument("--sleep-seconds", type=float, default=2.0, help="Espera entre reinícios em caso de erro.")
    parser.add_argument("--steps", type=int, default=0, help="Pass-through para engine (0=infinito).")
    args, extra = parser.parse_known_args()

    cmd = [sys.executable, "-m", "training.backtest.backtest_smart_engine"]
    if args.steps > 0:
        cmd += ["--steps", str(int(args.steps))]

    if args.safe_default:
        cmd += [
            "--panel", "0",
            "--progress-every", "10",
            "--summary-every", "50",
            "--heartbeat-seconds", "5",
            "--run-name", "continuous_safe_default",
        ]

    cmd += list(extra)

    print(f"[run_continuous] starting cmd={' '.join(cmd)}", flush=True)
    while True:
        proc = subprocess.run(cmd)
        if proc.returncode == 0:
            return 0
        print(f"[run_continuous] engine exited with code={proc.returncode}; retrying in {args.sleep_seconds:.1f}s", flush=True)
        time.sleep(max(0.5, float(args.sleep_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
