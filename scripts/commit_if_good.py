from __future__ import annotations

import json
import os
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "BD" / "lotofacil.db"
MARKER_PATH = ROOT / "scripts" / "ci_good_marker.json"

MIN_NEW_13 = int(os.getenv("MIN_NEW_13", "10"))

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sh(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out.strip()

def safe_table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None

def read_marker() -> dict:
    if MARKER_PATH.exists():
        try:
            return json.loads(MARKER_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_marker(data: dict) -> None:
    MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    MARKER_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main() -> None:
    if not DB_PATH.exists():
        print(f"[{now_str()}] DB não encontrado: {DB_PATH}")
        return

    marker = read_marker()
    last_id_13 = int(marker.get("last_mem_id_13", 0))

    conn = sqlite3.connect(str(DB_PATH))
    try:
        if not safe_table_exists(conn, "memoria_jogos"):
            print(f"[{now_str()}] Tabela memoria_jogos não existe. Nada para commitar.")
            return

        cur = conn.cursor()

        # Descobre o maior ID atual para 13+
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM memoria_jogos WHERE acertos >= 13")
        max_id_13 = int(cur.fetchone()[0] or 0)

        if max_id_13 <= last_id_13:
            print(f"[{now_str()}] Sem novas memórias 13+ desde o último marcador. (last={last_id_13}, max={max_id_13})")
            return

        # Conta novas memórias desde o marcador
        cur.execute(
            "SELECT COUNT(*) FROM memoria_jogos WHERE acertos >= 13 AND id > ?",
            (last_id_13,),
        )
        new_13 = int(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT COUNT(*) FROM memoria_jogos WHERE acertos >= 14 AND id > ?",
            (last_id_13,),
        )
        new_14 = int(cur.fetchone()[0] or 0)

        cur.execute(
            "SELECT COUNT(*) FROM memoria_jogos WHERE acertos = 15 AND id > ?",
            (last_id_13,),
        )
        new_15 = int(cur.fetchone()[0] or 0)

        should_commit = (new_15 >= 1) or (new_14 >= 1) or (new_13 >= MIN_NEW_13)

        print(f"[{now_str()}] Novas memórias desde id>{last_id_13}: 13+={new_13} | 14+={new_14} | 15={new_15}")
        print(f"[{now_str()}] Regra commit: 15>=1 OU 14>=1 OU 13+>={MIN_NEW_13} => {should_commit}")

        if not should_commit:
            # Atualiza marcador mesmo assim? Eu recomendo NÃO, pra acumular e commitar quando bater o mínimo.
            print(f"[{now_str()}] Ainda não bateu o mínimo. Não comitando.")
            return

    finally:
        conn.close()

    # Atualiza marcador (agora sim, pois vamos commitar)
    write_marker({
        "last_mem_id_13": max_id_13,
        "updated_at": now_str(),
        "min_new_13": MIN_NEW_13,
    })

    # Configura git
    sh(["git", "config", "user.name", "github-actions[bot]"])
    sh(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    # Stage DB + marker
    rc1, out1 = sh(["git", "add", str(DB_PATH), str(MARKER_PATH)])
    if rc1 != 0:
        print(out1)
        raise SystemExit(1)

    # Confere se tem diff staged
    rc2, out2 = sh(["git", "diff", "--cached", "--name-only"])
    if rc2 != 0:
        print(out2)
        raise SystemExit(1)

    if not out2.strip():
        print(f"[{now_str()}] Nada para commitar (diff vazio).")
        return

    msg = f"chore(db): snapshot aprendizagem 13+ (novas 13+={new_13},14+={new_14},15={new_15})"
    rc3, out3 = sh(["git", "commit", "-m", msg])
    if rc3 != 0:
        print(out3)
        raise SystemExit(1)

    rc4, out4 = sh(["git", "push"])
    if rc4 != 0:
        print(out4)
        raise SystemExit(1)

    print(f"[{now_str()}] ✅ Commit/push feito com sucesso!")

if __name__ == "__main__":
    main()
