import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk


ROOT_DIR = Path(__file__).resolve().parent


@dataclass
class CommandResult:
    label: str
    returncode: int


def get_venv_python() -> Path:
    if os.name == "nt":
        return ROOT_DIR / "venv" / "Scripts" / "python.exe"
    return ROOT_DIR / "venv" / "bin" / "python"


def resolve_python() -> Path:
    venv_python = get_venv_python()
    if venv_python.exists():
        return venv_python
    return Path(sys.executable)


class DesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("IA_TREVO4FOLHAS - Desktop")
        self.geometry("980x720")
        self.minsize(900, 650)
        self.configure(bg="#f4f6f8")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.result_queue: queue.Queue[CommandResult] = queue.Queue()

        self._build_ui()
        self.after(120, self._poll_queues)

    def _build_ui(self) -> None:
        header = ttk.Frame(self, padding=16)
        header.pack(fill="x")
        title = ttk.Label(
            header,
            text="IA_TREVO4FOLHAS - Central de Execução",
            font=("Segoe UI", 16, "bold"),
        )
        title.pack(anchor="w")

        subtitle = ttk.Label(
            header,
            text="Execute todos os scripts do projeto sem usar arquivos .bat.",
            font=("Segoe UI", 10),
            foreground="#555",
        )
        subtitle.pack(anchor="w", pady=(4, 0))

        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)

        left_panel = ttk.Frame(main)
        left_panel.pack(side="left", fill="y")

        right_panel = ttk.Frame(main)
        right_panel.pack(side="right", fill="both", expand=True)

        self.status_var = tk.StringVar(value="Pronto para executar.")
        status_label = ttk.Label(
            left_panel,
            textvariable=self.status_var,
            foreground="#0b5",
            wraplength=320,
        )
        status_label.pack(anchor="w", pady=(0, 16))

        buttons_frame = ttk.LabelFrame(left_panel, text="Ações principais", padding=12)
        buttons_frame.pack(fill="x", pady=(0, 16))

        self._add_button(
            buttons_frame,
            "Instalar/Atualizar ambiente",
            self.install_environment,
        )
        self._add_button(
            buttons_frame,
            "Inicializar banco de dados",
            self.start_database,
        )
        self._add_button(
            buttons_frame,
            "Atualizar concursos",
            self.update_contests,
        )
        self._add_button(
            buttons_frame,
            "Treinar IA (incremental + backtest)",
            self.train_incremental,
        )
        self._add_button(
            buttons_frame,
            "Gerar próximo concurso",
            self.generate_next_contest,
        )
        self._add_button(
            buttons_frame,
            "Atualizar banco de dados (merge)",
            self.update_database,
        )
        self._add_button(
            buttons_frame,
            "Status do aprendizado",
            self.learning_status,
        )
        self._add_button(
            buttons_frame,
            "Iniciar dashboard",
            self.start_dashboard,
        )

        config_frame = ttk.LabelFrame(left_panel, text="Configuração de geração", padding=12)
        config_frame.pack(fill="x", pady=(0, 16))

        self.perfil_var = tk.StringVar(value="agressivo")
        self.janela_var = tk.StringVar(value="300")
        self.per_brain_var = tk.StringVar(value="120")
        self.top_n_var = tk.StringVar(value="250")
        self.max_sim_var = tk.StringVar(value="0.78")
        self.size_var = tk.StringVar(value="15")
        self.qtd_var = tk.StringVar(value="10")
        self.second_size_var = tk.StringVar(value="18")
        self.second_qtd_var = tk.StringVar(value="8")

        self._add_entry(config_frame, "Perfil", self.perfil_var)
        self._add_entry(config_frame, "Janela", self.janela_var)
        self._add_entry(config_frame, "Per brain", self.per_brain_var)
        self._add_entry(config_frame, "Top N", self.top_n_var)
        self._add_entry(config_frame, "Max. similaridade", self.max_sim_var)
        self._add_entry(config_frame, "Tamanho principal", self.size_var)
        self._add_entry(config_frame, "Qtde principal", self.qtd_var)
        self._add_entry(config_frame, "Tamanho secundário", self.second_size_var)
        self._add_entry(config_frame, "Qtde secundária", self.second_qtd_var)

        log_frame = ttk.LabelFrame(right_panel, text="Log", padding=12)
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=20,
            wrap="word",
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
        )
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "Bem-vindo! Selecione uma ação à esquerda.\n")
        self.log_text.configure(state="disabled")

    def _add_button(self, parent: ttk.Frame, text: str, command: callable) -> None:
        button = ttk.Button(parent, text=text, command=command)
        button.pack(fill="x", pady=4)

    def _add_entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar) -> None:
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="x", pady=4)
        ttk.Label(wrapper, text=label, width=18).pack(side="left")
        ttk.Entry(wrapper, textvariable=variable, width=18).pack(side="right")

    def _poll_queues(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._append_log(message)
        except queue.Empty:
            pass

        try:
            while True:
                result = self.result_queue.get_nowait()
                color = "#16a34a" if result.returncode == 0 else "#dc2626"
                self.status_var.set(
                    f"{result.label} finalizado com código {result.returncode}."
                )
                self.status_var_label_color(color)
        except queue.Empty:
            pass

        self.after(120, self._poll_queues)

    def status_var_label_color(self, color: str) -> None:
        self.status_var.set(self.status_var.get())
        for widget in self.children.values():
            if isinstance(widget, ttk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label) and child.cget("textvariable") == str(
                        self.status_var
                    ):
                        child.configure(foreground=color)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _run_command(self, label: str, command: list[str], env: dict | None = None) -> None:
        def worker() -> None:
            self.log_queue.put(f"\n▶ {label}\n")
            self.log_queue.put(f"$ {' '.join(command)}\n")
            process = subprocess.Popen(
                command,
                cwd=ROOT_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            if process.stdout:
                for line in process.stdout:
                    self.log_queue.put(line)
            process.wait()
            self.result_queue.put(CommandResult(label=label, returncode=process.returncode))

        threading.Thread(target=worker, daemon=True).start()

    def _run_sequence(self, label: str, commands: list[list[str]]) -> None:
        def worker() -> None:
            self.log_queue.put(f"\n▶ {label}\n")
            for command in commands:
                self.log_queue.put(f"$ {' '.join(command)}\n")
                process = subprocess.Popen(
                    command,
                    cwd=ROOT_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                if process.stdout:
                    for line in process.stdout:
                        self.log_queue.put(line)
                process.wait()
                if process.returncode != 0:
                    self.result_queue.put(
                        CommandResult(label=label, returncode=process.returncode)
                    )
                    return
            self.result_queue.put(CommandResult(label=label, returncode=0))

        threading.Thread(target=worker, daemon=True).start()

    def install_environment(self) -> None:
        venv_python = get_venv_python()
        commands: list[list[str]] = []
        if not venv_python.exists():
            commands.append([sys.executable, "-m", "venv", "venv"])
        commands.extend(
            [
                [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
                [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
                [str(venv_python), "START/startBD.py"],
            ]
        )
        self._run_sequence("Instalação do ambiente", commands)

    def start_database(self) -> None:
        python_exec = resolve_python()
        self._run_command(
            "Inicialização do banco",
            [str(python_exec), "START/startBD.py"],
        )

    def update_contests(self) -> None:
        python_exec = resolve_python()
        self._run_command(
            "Atualização de concursos",
            [str(python_exec), "START/update_concursos.py"],
        )

    def train_incremental(self) -> None:
        python_exec = resolve_python()
        commands = [
            [str(python_exec), "-m", "training.trainer_v2"],
            [
                str(python_exec),
                "-m",
                "training.backtest.backtest_engine",
                "--hours",
                "24",
                "--block-size",
                "250",
                "--min-mem",
                "14",
                "--aggressive",
            ],
        ]
        self._run_sequence("Treino incremental", commands)

    def generate_next_contest(self) -> None:
        python_exec = resolve_python()
        command = [
            str(python_exec),
            "START/gerar_proximo_concurso.py",
            "--size",
            self.size_var.get(),
            "--qtd",
            self.qtd_var.get(),
            "--second-size",
            self.second_size_var.get(),
            "--second-qtd",
            self.second_qtd_var.get(),
            "--perfil",
            self.perfil_var.get(),
            "--janela",
            self.janela_var.get(),
            "--per-brain",
            self.per_brain_var.get(),
            "--top-n",
            self.top_n_var.get(),
            "--max-sim",
            self.max_sim_var.get(),
            "--salvar-db",
        ]
        self._run_command("Geração do próximo concurso", command)

    def update_database(self) -> None:
        python_exec = resolve_python()
        self._run_command(
            "Atualização do banco de dados",
            [str(python_exec), "scripts/merge_temp_dbs.py"],
        )

    def learning_status(self) -> None:
        python_exec = resolve_python()
        self._run_command(
            "Status do aprendizado",
            [str(python_exec), "START/status_aprendizado.py"],
        )

    def start_dashboard(self) -> None:
        python_exec = resolve_python()
        env = os.environ.copy()
        env.setdefault("HOST", "0.0.0.0")
        env.setdefault("PORT", "5000")
        self._run_command(
            "Dashboard",
            [str(python_exec), "-m", "src.web_dashboard"],
            env=env,
        )


if __name__ == "__main__":
    app = DesktopApp()
    app.mainloop()
