from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import sys

from flask import Flask, jsonify, redirect, render_template, request, url_for

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


app = Flask(__name__, template_folder="templates", static_folder="static")

REPORTS_DIR = ROOT / "reports"
REPORT_15 = REPORTS_DIR / "relatorio_avaliacao_15.json"
REPORT_18 = REPORTS_DIR / "relatorio_avaliacao_18.json"


@dataclass
class TaskStatus:
    status: str = "idle"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    last_message: str = ""
    log_path: Optional[Path] = None
    args: Dict[str, str] = field(default_factory=dict)


TASKS: Dict[str, TaskStatus] = {
    "avaliacao": TaskStatus(),
    "treino": TaskStatus(),
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_report(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def run_command(name: str, cmd: list[str], log_file: Path, args: Dict[str, str]) -> None:
    task = TASKS[name]
    task.status = "running"
    task.started_at = now_str()
    task.finished_at = None
    task.last_message = "Iniciando execução..."
    task.log_path = log_file
    task.args = args

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as fp:
        fp.write(f"[{task.started_at}] comando: {' '.join(cmd)}\n")
        fp.flush()
        process = subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, cwd=str(ROOT))
        code = process.wait()

    task.finished_at = now_str()
    if code == 0:
        task.status = "completed"
        task.last_message = "Execução concluída com sucesso."
    else:
        task.status = "failed"
        task.last_message = f"Falha na execução (exit code {code})."


def start_background_task(name: str, cmd: list[str], log_name: str, args: Dict[str, str]) -> None:
    log_file = REPORTS_DIR / log_name
    thread = threading.Thread(
        target=run_command,
        args=(name, cmd, log_file, args),
        daemon=True,
    )
    thread.start()


@app.route("/")
def index():
    relatorio_15 = load_report(REPORT_15)
    relatorio_18 = load_report(REPORT_18)
    return render_template(
        "dashboard.html",
        relatorio_15=relatorio_15,
        relatorio_18=relatorio_18,
        tasks=TASKS,
    )


@app.route("/avaliar", methods=["POST"])
def avaliar():
    if TASKS["avaliacao"].status == "running":
        return redirect(url_for("index"))

    janela = request.form.get("janela", "300")
    candidatos_15 = request.form.get("candidatos_15", "120")
    candidatos_18 = request.form.get("candidatos_18", "80")
    top_n = request.form.get("top_n", "60")
    avaliar_top_k_15 = request.form.get("avaliar_top_k_15", "60")
    avaliar_top_k_18 = request.form.get("avaliar_top_k_18", "40")
    max_concursos = request.form.get("max_concursos", "200")
    exploracao_15 = request.form.get("exploration_15", "0.12")
    exploracao_18 = request.form.get("exploration_18", "0.08")
    simular = request.form.get("simular_aprendizado", "true") == "true"

    cmd_15 = [
        sys.executable,
        "scripts/avaliar_desempenho.py",
        "--janela",
        janela,
        "--candidatos",
        candidatos_15,
        "--top-n",
        top_n,
        "--avaliar-top-k",
        avaliar_top_k_15,
        "--max-concursos",
        max_concursos,
        "--exploration-rate",
        exploracao_15,
        "--salvar-relatorio",
        str(REPORT_15),
    ]
    cmd_18 = [
        sys.executable,
        "scripts/avaliar_desempenho.py",
        "--janela",
        janela,
        "--candidatos",
        candidatos_18,
        "--top-n",
        top_n,
        "--avaliar-top-k",
        avaliar_top_k_18,
        "--max-concursos",
        max_concursos,
        "--exploration-rate",
        exploracao_18,
        "--salvar-relatorio",
        str(REPORT_18),
    ]
    if simular:
        cmd_15.append("--simular-aprendizado")
        cmd_18.append("--simular-aprendizado")

    args = {
        "janela": janela,
        "candidatos_15": candidatos_15,
        "candidatos_18": candidatos_18,
        "top_n": top_n,
        "avaliar_top_k_15": avaliar_top_k_15,
        "avaliar_top_k_18": avaliar_top_k_18,
        "max_concursos": max_concursos,
        "exploracao_15": exploracao_15,
        "exploracao_18": exploracao_18,
        "simular": str(simular),
    }

    def run_both() -> None:
        run_command("avaliacao", cmd_15, REPORTS_DIR / "avaliacao_15.log", args)
        if TASKS["avaliacao"].status == "completed":
            run_command("avaliacao", cmd_18, REPORTS_DIR / "avaliacao_18.log", args)

    thread = threading.Thread(target=run_both, daemon=True)
    thread.start()
    return redirect(url_for("index"))


@app.route("/treinar", methods=["POST"])
def treinar():
    if TASKS["treino"].status == "running":
        return redirect(url_for("index"))

    limite = request.form.get("limite", "")
    loop = request.form.get("loop", "false") == "true"
    sleep_min = request.form.get("sleep_min", "30")

    cmd = [sys.executable, "-m", "training.trainer_v2"]
    if loop:
        cmd.append("--loop")
        cmd.extend(["--sleep-min", sleep_min])
    if limite:
        cmd.extend(["--limite", limite])

    args = {"limite": limite, "loop": str(loop), "sleep_min": sleep_min}
    start_background_task("treino", cmd, "treino.log", args)
    return redirect(url_for("index"))


@app.route("/status/<task_name>")
def status(task_name: str):
    if task_name not in TASKS:
        return jsonify({"error": "task not found"}), 404
    task = TASKS[task_name]
    return jsonify(
        {
            "status": task.status,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
            "message": task.last_message,
            "args": task.args,
        }
    )


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()
