from __future__ import annotations

from datetime import datetime
import os
import sys
from typing import Any, Dict

_ANSI = {
    "reset": "\033[0m",
    "gray": "\033[90m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "cyan": "\033[96m",
    "white": "\033[97m",
    "magenta": "\033[95m",
}


def _try_enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import colorama  # type: ignore
        colorama.just_fix_windows_console()
    except Exception:
        # sem dependência obrigatória
        pass


def supports_ansi() -> bool:
    _try_enable_windows_ansi()
    if os.getenv("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    term = str(os.getenv("TERM", "")).lower()
    if term in {"", "dumb"} and os.name != "nt":
        return False
    return True


def colorize(text: str, color_name: str) -> str:
    if not supports_ansi():
        return str(text)
    c = _ANSI.get(str(color_name).lower(), "")
    if not c:
        return str(text)
    return f"{c}{text}{_ANSI['reset']}"


def _status_icon(status: str) -> str:
    m = {
        "warmup": "⚪",
        "learning": "🟢",
        "stable": "🟡",
        "regressing": "🔴",
        "green": "🟢",
        "yellow": "🟡",
        "red": "🔴",
    }
    return m.get(str(status).strip().lower(), "⚪")


def make_panel_line(data: Dict[str, Any]) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    status = str(data.get("status", "warmup"))
    icon = _status_icon(status)

    status_color = {
        "⚪": "gray",
        "🟢": "green",
        "🟡": "yellow",
        "🔴": "red",
    }.get(icon, "white")

    gov = str(data.get("governance_policy", "NORMAL"))
    gov_color = {
        "SAFE": "cyan",
        "NORMAL": "white",
        "AGGRESSIVE": "magenta",
        "AGGR": "magenta",
    }.get(gov.upper(), "white")

    p_status = colorize(icon, status_color)
    p_gov = colorize(gov, gov_color)

    conf = float(data.get("confidence", 0.0))
    delta14 = float(data.get("delta14", 0.0)) * 100.0
    reward = float(data.get("reward", 0.0))
    ent = float(data.get("entropy", 0.0))
    clone = float(data.get("clone", 0.0))
    cov = float(data.get("coverage", 0.0))
    step = int(data.get("step", 0))
    concurso = int(data.get("concurso", 0))

    return (
        f"[{now}] STATUS:{p_status}  GOV:{p_gov}  conf={conf:.2f}  "
        f"Δ14={delta14:+.1f}%  R={reward:+.2f}  ent={ent:.2f}  clone={clone:.2f}  "
        f"cov={cov:.2f}  step={step} N={concurso}"
    )
