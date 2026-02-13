from __future__ import annotations

import argparse

from data.BD.connection import get_conn
from training.reporting import queries


def resolve_run_id(conn, run_id: int | None, last_run: bool) -> int | None:
    if run_id is not None:
        return int(run_id)
    if last_run:
        row = conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return int(row[0]) if row else None
    return None


def build_report_text(conn, run_id: int, top_n: int = 5) -> str:
    info = queries.run_info(conn, run_id)
    artifacts = queries.run_artifacts(conn, run_id)
    summary = queries.overall_summary(conn, run_id)
    arms = queries.top_arms(conn, run_id, top_n=top_n)
    recipes = queries.top_recipes(conn, run_id, top_n=top_n)
    hit_dist = queries.hits_distribution(conn, run_id)
    div_mode = queries.diversity_by_mode(conn, run_id)
    fb = queries.fallback_rate(conn, run_id)
    sw = queries.mode_switch_rate(conn, run_id)
    gold, quar = queries.memory_growth(conn)
    exp_total, exp_pass = queries.experiments_summary(conn, run_id)

    lines = []
    lines.append(f"Run {run_id} | info={info}")
    lines.append(f"Config hash={artifacts.get('config_hash', 'n/a')} | seed={artifacts.get('seed', 'n/a')}")
    lines.append(
        f"steps={summary['steps']} reward_mean={summary['reward_mean']:.3f} best_hit={summary['best_hit']} 14+={summary['q14p']} 15={summary['q15']}"
    )
    lines.append(f"fallback_rate={fb:.3f} mode_switch_rate={sw:.3f}")
    lines.append(f"diversity_by_mode={div_mode}")
    lines.append(f"hits_distribution={hit_dist}")
    lines.append(f"gold={gold} quarantine={quar}")
    lines.append(f"experiments={exp_total} passed={exp_pass}")
    lines.append("Top arms:")
    for r in arms:
        lines.append(f"  - {r}")
    lines.append("Top recipes:")
    for r in recipes:
        lines.append(f"  - {r}")
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", type=int, default=None)
    p.add_argument("--last-run", action="store_true")
    p.add_argument("--top-n", type=int, default=5)
    args = p.parse_args()

    conn = get_conn()
    try:
        rid = resolve_run_id(conn, args.run_id, args.last_run)
        if rid is None:
            print("No run found.")
            return
        print(build_report_text(conn, rid, top_n=int(args.top_n)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
