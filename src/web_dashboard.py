from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sqlite3

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

from data.BD.connection import get_conn


app = Flask(__name__, template_folder="templates", static_folder="static")

REPORTS_DIR = ROOT / "reports"
REPORT_15 = REPORTS_DIR / "relatorio_avaliacao_15.json"
REPORT_18 = REPORTS_DIR / "relatorio_avaliacao_18.json"
REPORT_HTML = REPORTS_DIR / "dashboard.html"
REPORT_LOGS = {
    "avaliacao": [REPORTS_DIR / "avaliacao_15.log", REPORTS_DIR / "avaliacao_18.log"],
    "treino": [REPORTS_DIR / "treino.log"],
    "gerar_jogos": [REPORTS_DIR / "gerar_jogos.log"],
    "relatorio_html": [REPORTS_DIR / "gerar_dashboard.log"],
}

DB_DEFAULT_PATH = ROOT / "data" / "BD" / "lotofacil.db"


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
    "relatorio_html": TaskStatus(),
    "gerar_jogos": TaskStatus(),
}


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_log_path(task_name: str) -> Optional[Path]:
    task = TASKS.get(task_name)
    if task and task.log_path:
        return task.log_path
    log_list = REPORT_LOGS.get(task_name, [])
    return log_list[0] if log_list else None


def read_log_tail(path: Path, max_lines: int = 200) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    return "\n".join(lines[-max_lines:])


def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def get_db_path() -> Path:
    try:
        from config.paths import DB_PATH

        return Path(DB_PATH)
    except Exception:
        return DB_DEFAULT_PATH


def fetch_saved_games(conn: sqlite3.Connection, limit: int = 12) -> List[dict]:
    if not safe_table_exists(conn, "predicoes_proximo"):
        return []
    cur = conn.cursor()
    cur.execute(
        """
        SELECT concurso_previsto, tamanho,
               d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,
               score_final, perfil, timestamp
        FROM predicoes_proximo
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    games = []
    for row in rows:
        dezenas = [int(x) for x in row[2:20] if x is not None]
        games.append(
            {
                "concurso_previsto": row[0],
                "tamanho": row[1],
                "dezenas": dezenas,
                "score_final": row[20],
                "perfil": row[21] or "-",
                "timestamp": row[22] or "-",
            }
        )
    return games


def fetch_learning_history(conn: sqlite3.Connection, limit: int = 10) -> List[dict]:
    if not safe_table_exists(conn, "tentativas"):
        return []
    cur = conn.cursor()
    cur.execute(
        """
        SELECT concurso_n, concurso_n1, tipo_jogo, acertos, score, brain_id, timestamp
        FROM tentativas
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = cur.fetchall()
    history = []
    for row in rows:
        history.append(
            {
                "concurso_n": row[0],
                "concurso_n1": row[1],
                "tipo_jogo": row[2],
                "acertos": row[3],
                "score": row[4],
                "brain_id": row[5] or "-",
                "timestamp": row[6] or "-",
            }
        )
    return history


def fetch_learning_chart(conn: sqlite3.Connection) -> Dict[str, object]:
    if not safe_table_exists(conn, "memoria_jogos"):
        return {"labels": [], "values": [], "nivel": 0}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT acertos, COUNT(*)
        FROM memoria_jogos
        WHERE acertos >= 11
        GROUP BY acertos
        ORDER BY acertos
        """
    )
    rows = cur.fetchall()
    counts = {int(acertos): int(total) for acertos, total in rows}
    labels = [str(x) for x in range(11, 16)]
    values = [counts.get(x, 0) for x in range(11, 16)]
    total = sum(values)
    if total:
        weighted = sum((11 + i) * values[i] for i in range(len(values)))
        nivel = int(round(((weighted / total) - 11) / 4 * 100))
    else:
        nivel = 0
    return {"labels": labels, "values": values, "nivel": max(0, min(100, nivel))}


def fetch_learning_summary(conn: sqlite3.Connection) -> Dict[str, object]:
    summary = {"memoria_total": 0, "tentativas_total": 0, "acertos_14_15": 0}
    cur = conn.cursor()
    if safe_table_exists(conn, "memoria_jogos"):
        cur.execute("SELECT COUNT(*) FROM memoria_jogos")
        summary["memoria_total"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM memoria_jogos WHERE acertos >= 14")
        summary["acertos_14_15"] = cur.fetchone()[0]
    if safe_table_exists(conn, "tentativas"):
        cur.execute("SELECT COUNT(*) FROM tentativas")
        summary["tentativas_total"] = cur.fetchone()[0]
    return summary


def load_db_snapshot() -> Dict[str, object]:
    db_path = get_db_path()
    if not db_path.exists():
        return {
            "available": False,
            "path": str(db_path),
            "error": "Banco não encontrado. Rode START/startBD.py.",
            "saved_games": [],
            "learning_history": [],
            "learning_summary": {},
            "learning_chart": {"labels": [], "values": [], "nivel": 0},
        }

    try:
        with get_conn(str(db_path)) as conn:
            return {
                "available": True,
                "path": str(db_path),
                "error": None,
                "saved_games": fetch_saved_games(conn),
                "learning_history": fetch_learning_history(conn),
                "learning_summary": fetch_learning_summary(conn),
                "learning_chart": fetch_learning_chart(conn),
            }
    except sqlite3.Error as exc:
        return {
            "available": False,
            "path": str(db_path),
            "error": f"Falha ao acessar o banco: {exc}",
            "saved_games": [],
            "learning_history": [],
            "learning_summary": {},
            "learning_chart": {"labels": [], "values": [], "nivel": 0},
        }


def reset_task(name: str) -> None:
    task = TASKS[name]
    task.status = "idle"
    task.started_at = None
    task.finished_at = None
    task.last_message = ""
    task.log_path = None
    task.args = {}


def clear_task_artifacts(name: str) -> None:
    for log_path in REPORT_LOGS.get(name, []):
        if log_path.exists():
            log_path.unlink(missing_ok=True)
    if name == "avaliacao":
        for report in (REPORT_15, REPORT_18, REPORT_HTML):
            if report.exists():
                report.unlink(missing_ok=True)
        reset_task("relatorio_html")
    if name == "relatorio_html" and REPORT_HTML.exists():
        REPORT_HTML.unlink(missing_ok=True)
    reset_task(name)


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
    task = TASKS[name]
    task.status = "running"
    task.started_at = now_str()
    task.finished_at = None
    task.last_message = "Tarefa iniciada."
    task.log_path = log_file
    task.args = args
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
    db_snapshot = load_db_snapshot()
    return render_template(
        "dashboard.html",
        relatorio_15=relatorio_15,
        relatorio_18=relatorio_18,
        relatorio_html_disponivel=REPORT_HTML.exists(),
        tasks=TASKS,
        db_snapshot=db_snapshot,
    )


@app.route("/avaliar", methods=["POST"])
def avaliar():
    if TASKS["avaliacao"].status == "running":
        return redirect(url_for("index"))

    auto_clear = request.form.get("auto_clear") == "true"
    if auto_clear:
        clear_task_artifacts("avaliacao")

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
        if (
            TASKS["avaliacao"].status == "completed"
            and REPORT_15.exists()
            and REPORT_18.exists()
        ):
            run_command(
                "relatorio_html",
                [sys.executable, "scripts/gerar_dashboard_html.py"],
                REPORTS_DIR / "gerar_dashboard.log",
                {},
            )

    thread = threading.Thread(target=run_both, daemon=True)
    thread.start()
    return redirect(url_for("index"))


@app.route("/treinar", methods=["POST"])
def treinar():
    if TASKS["treino"].status == "running":
        return redirect(url_for("index"))

    auto_clear = request.form.get("auto_clear") == "true"
    if auto_clear:
        clear_task_artifacts("treino")

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


@app.route("/gerar-jogos", methods=["POST"])
def gerar_jogos():
    if TASKS["gerar_jogos"].status == "running":
        return redirect(url_for("index"))

    auto_clear = request.form.get("auto_clear") == "true"
    if auto_clear:
        clear_task_artifacts("gerar_jogos")

    size = request.form.get("size", "15")
    perfil = request.form.get("perfil", "balanceado")
    qtd = request.form.get("qtd", "6")
    salvar_db = request.form.get("salvar_db", "false") == "true"

    cmd = [
        sys.executable,
        "START/gerar_proximo_concurso.py",
        "--size",
        size,
        "--qtd",
        qtd,
        "--perfil",
        perfil,
    ]
    if salvar_db:
        cmd.append("--salvar-db")

    args = {
        "size": size,
        "perfil": perfil,
        "qtd": qtd,
        "salvar_db": str(salvar_db),
    }

    start_background_task("gerar_jogos", cmd, "gerar_jogos.log", args)
    return redirect(url_for("index"))


@app.route("/gerar-relatorio", methods=["POST"])
def gerar_relatorio():
    if TASKS["relatorio_html"].status == "running":
        return redirect(url_for("index"))

    auto_clear = request.form.get("auto_clear") == "true"
    if auto_clear:
        clear_task_artifacts("relatorio_html")

    start_background_task(
        "relatorio_html",
        [sys.executable, "scripts/gerar_dashboard_html.py"],
        "gerar_dashboard.log",
        {},
    )
    return redirect(url_for("index"))


@app.route("/relatorio-html")
def relatorio_html():
    if not REPORT_HTML.exists():
        return jsonify({"error": "relatorio not found"}), 404
    return send_file(REPORT_HTML, mimetype="text/html")


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


@app.route("/logs/<task_name>")
def logs(task_name: str):
    if task_name not in TASKS:
        return jsonify({"error": "task not found"}), 404
    log_path = get_log_path(task_name)
    if not log_path or not log_path.exists():
        return jsonify({"error": "log not found"}), 404
    content = read_log_tail(log_path)
    return app.response_class(content, mimetype="text/plain")


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
