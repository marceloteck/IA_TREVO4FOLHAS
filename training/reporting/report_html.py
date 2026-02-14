from __future__ import annotations

import argparse
from pathlib import Path

from data.BD.connection import get_conn
from training.reporting import queries


def _bar(v: float, vmax: float = 1.0, width: int = 24) -> str:
    n = int(max(0, min(width, round((v / max(1e-9, vmax)) * width))))
    return "█" * n + "·" * (width - n)


def _status_chip(status: str) -> str:
    s = str(status or "warmup").lower()
    colors = {"learning": "#1f9d55", "stable": "#b8860b", "regressing": "#cc3333", "warmup": "#888888"}
    labels = {"learning": "APRENDENDO", "stable": "ESTÁVEL", "regressing": "REGREDINDO", "warmup": "WARMUP"}
    return f"<span style='background:{colors.get(s, '#888')};color:white;padding:2px 6px;border-radius:9px'>{labels.get(s, 'WARMUP')}</span>"


def generate_html_report(conn, run_id: int, out_path: Path, top_n: int = 10) -> Path:
    info = queries.run_info(conn, run_id)
    artifacts = queries.run_artifacts(conn, run_id)
    summary = queries.overall_summary(conn, run_id)
    arms = queries.top_arms(conn, run_id, top_n=top_n)
    recipes = queries.top_recipes(conn, run_id, top_n=top_n)
    blocks = queries.reward_blocks(conn, run_id, block=20)
    hit_dist = queries.hits_distribution(conn, run_id)
    div_mode = queries.diversity_by_mode(conn, run_id)
    gold, quar = queries.memory_growth(conn)
    exp_total, exp_pass = queries.experiments_summary(conn, run_id)
    learning_timeline = queries.learning_status_timeline(conn, run_id)
    learning_trends = queries.learning_trend_series(conn, run_id)
    learning_modes = queries.learning_mode_changes(conn, run_id)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = [
        "<html><head><meta charset='utf-8'><title>Run Report</title>",
        "<style>body{font-family:Arial;padding:16px} .card{display:inline-block;border:1px solid #ccc;padding:10px;margin:6px} table{border-collapse:collapse} td,th{border:1px solid #ccc;padding:6px}</style>",
        "</head><body>",
        f"<h1>Run {run_id}</h1>",
        f"<p>config_hash={artifacts.get('config_hash','n/a')} | seed={artifacts.get('seed','n/a')} | info={info}</p>",
        f"<div class='card'>steps: {summary['steps']}</div><div class='card'>reward médio: {summary['reward_mean']:.3f}</div><div class='card'>best hit: {summary['best_hit']}</div><div class='card'>14+: {summary['q14p']} | 15: {summary['q15']}</div>",
        "<h2>Top Arms</h2><table><tr><th>arm</th><th>avg_reward</th><th>avg_hit</th><th>n</th></tr>",
    ]
    for a in arms:
        html.append(f"<tr><td>{a[0]}</td><td>{a[1]:.3f}</td><td>{a[2]:.3f}</td><td>{a[3]}</td></tr>")
    html.append("</table><h2>Top Recipes</h2><table><tr><th>recipe</th><th>avg_reward</th><th>avg_hit</th><th>n</th></tr>")
    for r in recipes:
        html.append(f"<tr><td>{r[0]}</td><td>{r[1]:.3f}</td><td>{r[2]:.3f}</td><td>{r[3]}</td></tr>")
    html.append("</table><h2>Reward por blocos</h2><pre>")
    for b in blocks:
        bar = _bar(float(b[1] if b[1] is not None else 0.0) + 5.0, vmax=10.0)
        html.append(f"bloco {b[0]} | {bar} | avg_reward={float(b[1] or 0):.3f} max_hit={int(b[2] or 0)}")
    html.append("</pre>")
    html.append(f"<h2>Hits</h2><p>{hit_dist}</p>")
    html.append(f"<h2>Diversidade por modo</h2><p>{div_mode}</p>")
    html.append(f"<h2>Memória</h2><p>gold={gold} quarantine={quar}</p>")
    html.append(f"<h2>Experimentos</h2><p>total={exp_total} passed={exp_pass}</p>")

    html.append("<h2>Linha do tempo de status (learning monitor)</h2>")
    if learning_timeline:
        html.append("<table><tr><th>step</th><th>status</th></tr>")
        for st, status in learning_timeline[-120:]:
            html.append(f"<tr><td>{int(st)}</td><td>{_status_chip(str(status))}</td></tr>")
        html.append("</table>")
    else:
        html.append("<p>Sem dados de status.</p>")

    html.append("<h2>Gráfico de tendência (Δreward / Δ14+ baseline)</h2><pre>")
    if learning_trends:
        for st, d_reward, d_q14 in learning_trends[-120:]:
            bar_reward = _bar(float(d_reward or 0.0) + 1.0, vmax=2.0, width=18)
            bar_q14 = _bar(float(d_q14 or 0.0) + 0.5, vmax=1.0, width=18)
            html.append(f"step {int(st):4d} | Δreward={float(d_reward or 0.0):+0.3f} {bar_reward} | Δ14+={float(d_q14 or 0.0):+0.3f} {bar_q14}")
    else:
        html.append("Sem dados de tendência.")
    html.append("</pre>")

    html.append("<h2>Histórico de mudanças de modo</h2>")
    if learning_modes:
        html.append("<table><tr><th>step</th><th>modo</th><th>forçado</th><th>resgate</th></tr>")
        for st, mode, forced, rescue in learning_modes[-120:]:
            html.append(f"<tr><td>{int(st)}</td><td>{mode or '-'}</td><td>{forced or '-'}</td><td>{'sim' if int(rescue or 0) else 'não'}</td></tr>")
        html.append("</table>")
    else:
        html.append("<p>Sem histórico de modo.</p>")

    html.append("</body></html>")

    out_path.write_text("\n".join(html), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--out", type=str, default=None)
    p.add_argument("--top-n", type=int, default=10)
    args = p.parse_args()

    conn = get_conn()
    try:
        out = Path(args.out) if args.out else Path("reports") / f"run_{int(args.run_id)}.html"
        path = generate_html_report(conn, int(args.run_id), out, top_n=int(args.top_n))
        print(str(path))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
