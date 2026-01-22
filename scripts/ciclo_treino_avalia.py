from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class AjusteConfig:
    cycles: int
    train_limit: int
    exploration_rate: float
    max_brain_share: float
    exploration_step: float
    exploration_min: float
    exploration_max: float
    eval_params: Dict[str, Any]


DEFAULT_CONFIG = AjusteConfig(
    cycles=3,
    train_limit=200,
    exploration_rate=0.12,
    max_brain_share=0.4,
    exploration_step=0.02,
    exploration_min=0.04,
    exploration_max=0.2,
    eval_params={
        "janela": 300,
        "candidatos": 120,
        "top_n": 60,
        "avaliar_top_k": 60,
        "max_concursos": 200,
        "simular_aprendizado": True,
    },
)


def load_config(path: Path) -> AjusteConfig:
    if not path.exists():
        return DEFAULT_CONFIG
    raw = json.loads(path.read_text(encoding="utf-8"))
    eval_params = raw.get("eval_params", {})
    return AjusteConfig(
        cycles=int(raw.get("cycles", DEFAULT_CONFIG.cycles)),
        train_limit=int(raw.get("train_limit", DEFAULT_CONFIG.train_limit)),
        exploration_rate=float(raw.get("exploration_rate", DEFAULT_CONFIG.exploration_rate)),
        max_brain_share=float(raw.get("max_brain_share", DEFAULT_CONFIG.max_brain_share)),
        exploration_step=float(raw.get("exploration_step", DEFAULT_CONFIG.exploration_step)),
        exploration_min=float(raw.get("exploration_min", DEFAULT_CONFIG.exploration_min)),
        exploration_max=float(raw.get("exploration_max", DEFAULT_CONFIG.exploration_max)),
        eval_params={**DEFAULT_CONFIG.eval_params, **eval_params},
    )


def save_config(path: Path, config: AjusteConfig) -> None:
    payload = {
        "cycles": config.cycles,
        "train_limit": config.train_limit,
        "exploration_rate": config.exploration_rate,
        "max_brain_share": config.max_brain_share,
        "exploration_step": config.exploration_step,
        "exploration_min": config.exploration_min,
        "exploration_max": config.exploration_max,
        "eval_params": config.eval_params,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def run_command(label: str, cmd: list[str], env: Dict[str, str]) -> None:
    print(f"\n▶ {label}: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, env=env, cwd=str(ROOT))


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def ajustar_exploracao(config: AjusteConfig, report: Dict[str, Any]) -> float:
    resumo = report.get("resumo", {})
    dados_15 = resumo.get("15", {})
    dados_18 = resumo.get("18", {})
    q14_15 = int(dados_15.get("q14+", 0))
    q14_18 = int(dados_18.get("q14+", 0))

    nova = config.exploration_rate
    if q14_15 == 0:
        nova += config.exploration_step
    elif q14_15 >= 2 and q14_18 >= 20:
        nova -= config.exploration_step / 2.0

    return clamp(nova, config.exploration_min, config.exploration_max)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ciclo automático: treina -> avalia -> ajusta -> treina")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "ciclo_treino_avalia.json",
        help="Arquivo de configuração do ciclo.",
    )
    args = parser.parse_args()

    config_path: Path = args.config
    config = load_config(config_path)
    save_config(config_path, config)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    reports_dir = ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for ciclo in range(1, config.cycles + 1):
        print("\n==============================")
        print(f"🚀 CICLO {ciclo}/{config.cycles}")
        print("==============================")

        run_command(
            "Treinamento",
            [
                sys.executable,
                "-m",
                "training.trainer_v2",
                "--limite",
                str(config.train_limit),
                "--exploration-rate",
                str(config.exploration_rate),
                "--max-brain-share",
                str(config.max_brain_share),
            ],
            env,
        )

        report_path = reports_dir / f"relatorio_ciclo_{ciclo}.json"
        eval_cmd = [
            sys.executable,
            "scripts/avaliar_desempenho.py",
            "--janela",
            str(config.eval_params["janela"]),
            "--candidatos",
            str(config.eval_params["candidatos"]),
            "--top-n",
            str(config.eval_params["top_n"]),
            "--avaliar-top-k",
            str(config.eval_params["avaliar_top_k"]),
            "--max-concursos",
            str(config.eval_params["max_concursos"]),
            "--exploration-rate",
            str(config.exploration_rate),
            "--salvar-relatorio",
            str(report_path),
        ]
        if config.eval_params.get("simular_aprendizado", False):
            eval_cmd.append("--simular-aprendizado")

        run_command("Avaliação", eval_cmd, env)

        report = json.loads(report_path.read_text(encoding="utf-8"))
        nova_exploracao = ajustar_exploracao(config, report)
        print(
            f"\n🔧 Ajuste exploration_rate: {config.exploration_rate:.3f} -> {nova_exploracao:.3f}"
        )
        config.exploration_rate = nova_exploracao
        save_config(config_path, config)

    print("\n✅ Ciclo concluído.")


if __name__ == "__main__":
    main()
