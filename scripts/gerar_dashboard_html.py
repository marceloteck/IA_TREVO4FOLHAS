from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
REPORT_15 = REPORTS_DIR / "relatorio_avaliacao_15.json"
REPORT_18 = REPORTS_DIR / "relatorio_avaliacao_18.json"
OUTPUT = REPORTS_DIR / "dashboard.html"


def load_report(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_section(title: str, report: dict | None, key: str) -> str:
    if not report:
        return f"<div class='card'><h3>{title}</h3><p class='muted'>Sem relatório disponível.</p></div>"
    resumo = report.get("resumo", {}).get(key, {})
    return f"""
    <div class="card">
      <h3>{title}</h3>
      <div class="metrics">
        <div class="metric"><span>Média de acertos</span><strong>{resumo.get("media_acertos", "-")}</strong></div>
        <div class="metric"><span>Melhor resultado</span><strong>{resumo.get("melhor", "-")}</strong></div>
        <div class="metric"><span>Quase acertos (11-13)</span><strong>{resumo.get("quase_acertos_11_13", "-")}</strong></div>
        <div class="metric"><span>Foco 14/15</span><strong>{resumo.get("foco_14_15", "-")}</strong></div>
      </div>
      <p class="muted">Atualizado em {report.get("timestamp", "-")}</p>
    </div>
    """


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_15 = load_report(REPORT_15)
    report_18 = load_report(REPORT_18)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def build_brain_list(title: str, report: dict | None, key: str) -> str:
        if not report or not report.get("brains"):
            return f"<div class='card'><h3>{title}</h3><p class='muted'>Sem dados de cérebros.</p></div>"
        items = list(report["brains"].items())[:8]
        rows = "".join(
            f"<li><strong>{brain_id}</strong> — Top1: {info.get(f'top1_{key}', 0)} | Gerados: {info.get(f'generated_{key}', 0)} | Média acertos (topK): {info.get(f'avg_acertos_topk_{key}', 0)}</li>"
            for brain_id, info in items
        )
        return f"<div class='card'><h3>{title}</h3><ul class='list'>{rows}</ul></div>"

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>IA Trevo4Folhas — Relatório</title>
        <style>
          :root {{
            color-scheme: dark;
            --bg: #0b0f1a;
            --card: #141a2a;
            --muted: #94a3b8;
            --accent: #22c55e;
            --border: #1f2a44;
          }}
          * {{
            box-sizing: border-box;
            font-family: "Inter", "Segoe UI", sans-serif;
          }}
          body {{
            margin: 0;
            background: var(--bg);
            color: #e2e8f0;
          }}
          header {{
            padding: 24px 32px;
            border-bottom: 1px solid var(--border);
            background: linear-gradient(120deg, #0b1224 0%, #111a33 100%);
          }}
          main {{
            padding: 24px 32px 48px;
            display: grid;
            gap: 24px;
          }}
          .grid {{
            display: grid;
            gap: 20px;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          }}
          .card {{
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 18px;
          }}
          .metrics {{
            display: grid;
            gap: 12px;
          }}
          .metric {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 8px 12px;
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.7);
          }}
          .metric span {{
            color: var(--muted);
          }}
          .list {{
            list-style: none;
            padding: 0;
            margin: 0;
          }}
          .list li {{
            padding: 6px 0;
            border-bottom: 1px solid rgba(148, 163, 184, 0.15);
            font-size: 13px;
            color: var(--muted);
          }}
          .muted {{
            color: var(--muted);
            font-size: 12px;
          }}
        </style>
      </head>
      <body>
        <header>
          <h1>IA Trevo4Folhas — Relatório Executivo</h1>
          <p class="muted">Gerado em {now_str}</p>
        </header>
        <main>
          <section class="grid">
            {build_section("Relatório 15 dezenas", report_15, "15")}
            {build_section("Relatório 18 dezenas", report_18, "18")}
          </section>
          <section class="grid">
            {build_brain_list("Top cérebros (15 dezenas)", report_15, "15")}
            {build_brain_list("Top cérebros (18 dezenas)", report_18, "18")}
          </section>
        </main>
      </body>
    </html>
    """

    OUTPUT.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
