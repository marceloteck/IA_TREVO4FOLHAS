from __future__ import annotations

import json
import os
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "BD" / "lotofacil.db"
MARKER_PATH = ROOT / "scripts" / "ci_good_marker.json"

# Quantas novas memórias 13+ para permitir commit (se não tiver 14/15)
MIN_NEW_13 = int(os.getenv("MIN_NEW_13", "10"))

# branch alvo (no actions geralmente é main)
TARGET_BRANCH = os.getenv("TARGET_BRANCH", "main")

# Quantas tentativas de push (com fetch/rebase entre elas)
PUSH_RETRIES = int(os.getenv("PUSH_RETRIES", "3"))

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _print(msg: str) -> None:
    print(f"[{now_str()}] {msg}")

def sh(cmd: list[str], check: bool = False) -> Tuple[int, str]:
    """
    Executa comando no ROOT e retorna (rc, output combinado).
    Se check=True, levanta SystemExit em rc != 0.
    """
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    out = out.strip()
    if check and p.returncode != 0:
        _print(f"[ERRO] cmd falhou: {' '.join(cmd)}")
        if out:
            print(out)
        raise SystemExit(p.returncode)
    return p.returncode, out

def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def read_marker() -> Dict:
    if MARKER_PATH.exists():
        try:
            return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_marker(data: Dict) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def compute_new_memory_stats(db_path: Path, last_id_13: int) -> Optional[Dict[str, int]]:
    """
    Retorna:
      {
        "max_id_13": int,
        "new_13": int,
        "new_14": int,
        "new_15": int
      }
    ou None se não der.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        if not safe_table_exists(conn, "memoria_jogos"):
            return None

        cur = conn.cursor()

        cur.execute("SELECT COALESCE(MAX(id), 0) FROM memoria_jogos WHERE acertos >= 13")
        max_id_13 = int(cur.fetchone()[0] or 0)

        if max_id_13 <= last_id_13:
            return {
                "max_id_13": max_id_13,
                "new_13": 0,
                "new_14": 0,
                "new_15": 0,
            }

        cur.execute("SELECT COUNT(*) FROM memoria_jogos WHERE acertos >= 13 AND id > ?", (last_id_13,))
        new_13 = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM memoria_jogos WHERE acertos >= 14 AND id > ?", (last_id_13,))
        new_14 = int(cur.fetchone()[0] or 0)

        cur.execute("SELECT COUNT(*) FROM memoria_jogos WHERE acertos = 15 AND id > ?", (last_id_13,))
        new_15 = int(cur.fetchone()[0] or 0)

        return {
            "max_id_13": max_id_13,
            "new_13": new_13,
            "new_14": new_14,
            "new_15": new_15,
        }
    finally:
        conn.close()

def configure_git_identity() -> None:
    sh(["git", "config", "user.name", "github-actions[bot]"])
    sh(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])

def ensure_on_branch(branch: str) -> None:
    # garante que o working tree está no branch esperado (actions normalmente já está)
    sh(["git", "checkout", branch], check=False)

def sync_with_remote(branch: str) -> None:
    """
    Faz fetch e tenta rebase no remoto.
    Não falha hard se rebase der conflito (apenas retorna e o push vai falhar, mas tentaremos de novo).
    """
    sh(["git", "fetch", "origin", branch], check=False)
    # rebase “melhor” para actions; se der conflito, aborta para não travar
    rc, out = sh(["git", "rebase", f"origin/{branch}"], check=False)
    if rc != 0:
        _print("[WARN] rebase falhou (possível conflito). Abortando rebase e seguindo.")
        sh(["git", "rebase", "--abort"], check=False)
        if out:
            print(out)

def stage_changes(paths: list[Path]) -> None:
    cmd = ["git", "add"] + [str(p) for p in paths]
    sh(cmd, check=True)

def has_staged_changes() -> bool:
    rc, out = sh(["git", "diff", "--cached", "--name-only"], check=True)
    return bool(out.strip())

def commit_changes(message: str) -> None:
    sh(["git", "commit", "-m", message], check=True)

def push_with_retries(branch: str, retries: int) -> bool:
    """
    Tenta push. Se rejeitar, faz fetch/rebase e tenta de novo.
    Retorna True se push ok.
    """
    for attempt in range(1, max(1, retries) + 1):
        rc, out = sh(["git", "push", "origin", branch], check=False)
        if rc == 0:
            return True

        _print(f"[WARN] push falhou (tentativa {attempt}/{retries}).")
        if out:
            print(out)

        # Sincroniza e tenta novamente
        sync_with_remote(branch)

    return False

def main() -> None:
    if not DB_PATH.exists():
        _print(f"DB não encontrado: {DB_PATH}")
        return

    marker = read_marker()
    last_id_13 = int(marker.get("last_mem_id_13", 0))

    stats = compute_new_memory_stats(DB_PATH, last_id_13=last_id_13)
    if stats is None:
        _print("Tabela memoria_jogos não existe. Nada para commitar.")
        return

    max_id_13 = int(stats["max_id_13"])
    new_13 = int(stats["new_13"])
    new_14 = int(stats["new_14"])
    new_15 = int(stats["new_15"])

    _print(f"Novas memórias desde id>{last_id_13}: 13+={new_13} | 14+={new_14} | 15={new_15}")
    should_commit = (new_15 >= 1) or (new_14 >= 1) or (new_13 >= MIN_NEW_13)
    _print(f"Regra commit: 15>=1 OU 14>=1 OU 13+>={MIN_NEW_13} => {should_commit}")

    if not should_commit:
        _print("Ainda não bateu o mínimo. Não comitando.")
        return

    # ✅ ATENÇÃO: marker NÃO deve ser gravado antes do push ter sucesso.
    # vamos preparar o conteúdo do marker, mas só escrever se push ok.
    marker_next = {
        "last_mem_id_13": max_id_13,
        "updated_at": now_str(),
        "min_new_13": MIN_NEW_13,
        "branch": TARGET_BRANCH,
    }

    configure_git_identity()
    ensure_on_branch(TARGET_BRANCH)

    # antes de commitar, sincroniza com remoto para evitar reject
    sync_with_remote(TARGET_BRANCH)

    # escreve marker no disco (para entrar no commit)
    write_marker(marker_next)

    # stage DB + marker
    stage_changes([DB_PATH, MARKER_PATH])

    if not has_staged_changes():
        _print("Nada para commitar (diff vazio).")
        return

    msg = f"chore(db): snapshot aprendizagem (novas 13+={new_13},14+={new_14},15={new_15})"
    commit_changes(msg)

    ok = push_with_retries(TARGET_BRANCH, retries=PUSH_RETRIES)

    if not ok:
        # push falhou, mas commit ficou local do runner
        # não atualizamos o marker "remoto" ainda, mas ele já está no commit local.
        _print("[ERRO] Não consegui dar push após tentativas.")
        _print("Dica: isso acontece quando outro workflow fez push ao mesmo tempo.")
        _print("Sugestão: serialize workflows (concurrency) ou use artifact para salvar o DB.")
        raise SystemExit(1)

    _print("✅ Commit/push feito com sucesso!")

if __name__ == "__main__":
    main()
