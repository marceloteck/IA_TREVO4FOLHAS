from __future__ import annotations

import sqlite3


def _fetchall(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    try:
        return conn.execute(sql, params).fetchall()
    except Exception:
        return []


def top_arms(conn: sqlite3.Connection, run_id: int, top_n: int = 5):
    return _fetchall(
        conn,
        """
        SELECT d.arm, AVG(o.reward) avg_reward, AVG(o.hit_max) avg_hit, COUNT(*) n
        FROM decisions d JOIN outcomes o ON d.run_id=o.run_id AND d.step=o.step
        WHERE d.run_id=?
        GROUP BY d.arm
        ORDER BY avg_reward DESC, avg_hit DESC
        LIMIT ?
        """,
        (int(run_id), int(top_n)),
    )


def top_recipes(conn: sqlite3.Connection, run_id: int, top_n: int = 5):
    return _fetchall(
        conn,
        """
        SELECT d.recipe, AVG(o.reward) avg_reward, AVG(o.hit_max) avg_hit, COUNT(*) n
        FROM decisions d JOIN outcomes o ON d.run_id=o.run_id AND d.step=o.step
        WHERE d.run_id=?
        GROUP BY d.recipe
        ORDER BY avg_reward DESC, avg_hit DESC
        LIMIT ?
        """,
        (int(run_id), int(top_n)),
    )


def reward_blocks(conn: sqlite3.Connection, run_id: int, block: int = 20):
    return _fetchall(
        conn,
        """
        SELECT ((step-1)/?) as block_id, AVG(reward) avg_reward, MAX(hit_max) max_hit
        FROM outcomes
        WHERE run_id=?
        GROUP BY ((step-1)/?)
        ORDER BY block_id
        """,
        (int(block), int(run_id), int(block)),
    )


def hits_distribution(conn: sqlite3.Connection, run_id: int):
    return dict(
        _fetchall(
            conn,
            """
            SELECT hit_max, COUNT(*)
            FROM outcomes WHERE run_id=?
            GROUP BY hit_max ORDER BY hit_max DESC
            """,
            (int(run_id),),
        )
    )


def diversity_by_mode(conn: sqlite3.Connection, run_id: int):
    return _fetchall(
        conn,
        """
        SELECT CASE WHEN CAST(json_extract(t.summary_json, '$.mode') AS TEXT) IS NULL THEN 'unknown' ELSE CAST(json_extract(t.summary_json, '$.mode') AS TEXT) END as mode,
               AVG(o.diversity) as avg_div
        FROM outcomes o
        LEFT JOIN telemetry_step_summaries t ON o.run_id=t.run_id AND o.step=t.step
        WHERE o.run_id=?
        GROUP BY mode
        """,
        (int(run_id),),
    )


def fallback_rate(conn: sqlite3.Connection, run_id: int):
    rows = _fetchall(conn, "SELECT AVG(fallback_used), COUNT(*) FROM decisions WHERE run_id=?", (int(run_id),))
    if not rows:
        return 0.0
    return float(rows[0][0] or 0.0)


def mode_switch_rate(conn: sqlite3.Connection, run_id: int):
    rows = _fetchall(
        conn,
        "SELECT step, json_extract(summary_json, '$.mode') FROM telemetry_step_summaries WHERE run_id=? ORDER BY step",
        (int(run_id),),
    )
    if len(rows) < 2:
        return 0.0
    switches = 0
    prev = rows[0][1]
    for _, m in rows[1:]:
        if m != prev:
            switches += 1
        prev = m
    return switches / float(max(1, len(rows) - 1))


def memory_growth(conn: sqlite3.Connection):
    gold = _fetchall(conn, "SELECT COUNT(*) FROM memoria_jogos_gold")
    quar = _fetchall(conn, "SELECT COUNT(*) FROM memoria_jogos_quarantine")
    return int(gold[0][0]) if gold else 0, int(quar[0][0]) if quar else 0


def experiments_summary(conn: sqlite3.Connection, run_id: int):
    rows = _fetchall(conn, "SELECT COUNT(*), SUM(CASE WHEN passes=1 THEN 1 ELSE 0 END) FROM experiments WHERE run_id=?", (int(run_id),))
    if not rows:
        return 0, 0
    return int(rows[0][0] or 0), int(rows[0][1] or 0)


def run_info(conn: sqlite3.Connection, run_id: int):
    rows = _fetchall(conn, "SELECT id, started_at, mode, config_hash, seed, status FROM runs WHERE id=?", (int(run_id),))
    return rows[0] if rows else None


def run_artifacts(conn: sqlite3.Connection, run_id: int):
    return dict(_fetchall(conn, "SELECT key, value FROM run_artifacts WHERE run_id=?", (int(run_id),)))


def overall_summary(conn: sqlite3.Connection, run_id: int):
    rows = _fetchall(conn, "SELECT COUNT(*), AVG(reward), MAX(hit_max), SUM(CASE WHEN hit_max>=14 THEN 1 ELSE 0 END), SUM(CASE WHEN hit_max>=15 THEN 1 ELSE 0 END) FROM outcomes WHERE run_id=?", (int(run_id),))
    if not rows:
        return {"steps": 0, "reward_mean": 0.0, "best_hit": 0, "q14p": 0, "q15": 0}
    r = rows[0]
    return {
        "steps": int(r[0] or 0),
        "reward_mean": float(r[1] or 0.0),
        "best_hit": int(r[2] or 0),
        "q14p": int(r[3] or 0),
        "q15": int(r[4] or 0),
    }



def get_tuning_metrics(conn: sqlite3.Connection, run_id: int):
    summary = overall_summary(conn, run_id)
    fb = fallback_rate(conn, run_id)
    div_rows = _fetchall(conn, "SELECT AVG(diversity) FROM outcomes WHERE run_id=?", (int(run_id),))
    div_mean = float(div_rows[0][0] or 0.0) if div_rows else 0.0
    rescue_rows = _fetchall(
        conn,
        "SELECT AVG(CASE WHEN json_extract(summary_json, '$.rescue_mode') THEN 1.0 ELSE 0.0 END) FROM telemetry_step_summaries WHERE run_id=?",
        (int(run_id),),
    )
    rescue_rate = float(rescue_rows[0][0] or 0.0) if rescue_rows else 0.0
    step_rows = _fetchall(conn, "SELECT MIN(created_at), MAX(created_at), COUNT(*) FROM outcomes WHERE run_id=?", (int(run_id),))
    avg_step_seconds = 0.0
    if step_rows and step_rows[0][2] and step_rows[0][0] and step_rows[0][1]:
        # approximation intentionally lightweight
        avg_step_seconds = 0.0
    exp = experiments_summary(conn, run_id)
    baseline_fail = exp[0] > 0 and exp[1] / float(max(1, exp[0])) < 0.3
    return {
        "steps": summary.get("steps", 0),
        "fallback_rate": fb,
        "diversity_mean": div_mean,
        "rescue_rate": rescue_rate,
        "avg_step_seconds": avg_step_seconds,
        "baseline_fail": baseline_fail,
    }


def learning_status_timeline(conn: sqlite3.Connection, run_id: int):
    return _fetchall(
        conn,
        """
        SELECT step,
               CAST(json_extract(summary_json, '$.learning_monitor.status') AS TEXT) as status
        FROM telemetry_step_summaries
        WHERE run_id=?
          AND json_extract(summary_json, '$.learning_monitor.status') IS NOT NULL
        ORDER BY step ASC
        """,
        (int(run_id),),
    )


def learning_mode_changes(conn: sqlite3.Connection, run_id: int):
    return _fetchall(
        conn,
        """
        SELECT step,
               CAST(json_extract(summary_json, '$.mode') AS TEXT) as mode,
               CAST(json_extract(summary_json, '$.learning_monitor.policy.force_mode') AS TEXT) as forced_mode,
               CAST(json_extract(summary_json, '$.learning_monitor.policy.rescue_mode') AS INTEGER) as rescue_mode
        FROM telemetry_step_summaries
        WHERE run_id=?
        ORDER BY step ASC
        """,
        (int(run_id),),
    )


def learning_trend_series(conn: sqlite3.Connection, run_id: int):
    return _fetchall(
        conn,
        """
        SELECT step,
               CAST(json_extract(summary_json, '$.learning_monitor.trend.delta_reward') AS REAL) as delta_reward,
               CAST(json_extract(summary_json, '$.learning_monitor.baseline.delta_q14_vs_baseline') AS REAL) as delta_q14_baseline
        FROM telemetry_step_summaries
        WHERE run_id=?
          AND json_extract(summary_json, '$.learning_monitor.status') IS NOT NULL
        ORDER BY step ASC
        """,
        (int(run_id),),
    )


def governance_timeline(conn: sqlite3.Connection, run_id: int):
    return _fetchall(
        conn,
        """
        SELECT step, status, confidence, delta14, reward_avg, trend, policy, reason
        FROM governance_decisions
        WHERE run_id=?
        ORDER BY step ASC
        """,
        (int(run_id),),
    )
