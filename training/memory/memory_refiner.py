from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from training.memory.memory_audit import audit_action, ensure_memory_tables
from training.memory.memory_compress import compress_gold
from training.memory.memory_scoring import score_memory_item


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class MemoryRefiner:
    def __init__(self, db_conn, cfg: dict):
        self.conn = db_conn
        self.cfg = dict(cfg or {})
        self.enabled = bool(self.cfg.get("enabled", True))
        ensure_memory_tables(self.conn)
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memoria_jogos'"
        ).fetchone()
        if row is not None:
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_memoria_jogos_origem ON memoria_jogos(origem)")
            self.conn.commit()

    def _get_last_id(self) -> int:
        row = self.conn.execute("SELECT last_memoria_id FROM memory_refiner_state WHERE id=1").fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _set_last_id(self, last_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO memory_refiner_state(id, last_memoria_id, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                last_memoria_id=excluded.last_memoria_id,
                updated_at=excluded.updated_at
            """,
            (int(last_id), now_str()),
        )

    def _strategy_recent_count(self, origem: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM memoria_jogos WHERE origem=?", (str(origem),)
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def _strategy_recent_counts(self, origens: set[str]) -> dict[str, int]:
        if not origens:
            return {}

        placeholders = ",".join("?" for _ in origens)
        rows = self.conn.execute(
            f"SELECT origem, COUNT(*) FROM memoria_jogos WHERE origem IN ({placeholders}) GROUP BY origem",
            tuple(str(o) for o in origens),
        ).fetchall()
        return {str(origem): int(total) for origem, total in rows}

    def run_batch(self, batch_size: int = 1000) -> dict:
        if not self.enabled:
            return {"processed": 0, "gold": 0, "quarantine": 0, "ignored": 0}

        last_id = self._get_last_id()
        rows = self.conn.execute(
            """
            SELECT id, concurso_n1, tipo_jogo,
                   d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18,
                   acertos, origem
            FROM memoria_jogos
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(last_id), int(batch_size)),
        ).fetchall()

        if not rows:
            return {"processed": 0, "gold": 0, "quarantine": 0, "ignored": 0}

        gold_th = float(self.cfg.get("gold_threshold", 0.72))
        quar_th = float(self.cfg.get("quarantine_threshold", 0.35))
        min_hit_gold = int(self.cfg.get("min_hit_gold", 13))

        n_gold = n_quar = n_ign = 0
        max_id = last_id
        strategy_counts = self._strategy_recent_counts({str(row[-1] or "") for row in rows})

        for row in rows:
            (
                mem_id,
                concurso_ref,
                tipo_jogo,
                *dezenas_raw,
                acertos,
                origem,
            ) = row
            dezenas = [int(x) for x in dezenas_raw if x is not None]
            strategy_recent_count = int(strategy_counts.get(str(origem or ""), 0))

            dup_row = self.conn.execute(
                "SELECT 1 FROM memoria_jogos_gold WHERE dezenas_json=? LIMIT 1",
                (json.dumps(dezenas, ensure_ascii=False),),
            ).fetchone()
            is_clone = dup_row is not None

            score, flags, extra = score_memory_item(
                dezenas=dezenas,
                tipo_jogo=int(tipo_jogo),
                hit=int(acertos),
                meta={
                    "arm": str(origem or "").split(":")[1] if ":" in str(origem or "") else "-",
                    "recipe": str(origem or "").split(":")[2] if ":" in str(origem or "") and len(str(origem).split(":")) > 2 else "-",
                    "brains_signature": str(origem or "")[-24:],
                    "strategy_recent_count": strategy_recent_count,
                    "is_clone": is_clone,
                },
                cfg=self.cfg,
            )

            dezenas_json = json.dumps(dezenas, ensure_ascii=False)
            target = "ignore"
            if score >= gold_th and int(acertos) >= min_hit_gold:
                target = "gold"
            elif score < quar_th or any(f in {"clone", "overfit_suspect", "low_hit"} for f in flags):
                target = "quarantine"

            if target == "gold":
                self.conn.execute(
                    """
                    INSERT INTO memoria_jogos_gold(
                        source_memoria_id, concurso_ref, tipo_jogo, dezenas_json, hit, quality_score,
                        context_signature, strategy_signature, diversity_tag, validated, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        int(mem_id),
                        int(concurso_ref),
                        int(tipo_jogo),
                        dezenas_json,
                        int(acertos),
                        float(score),
                        str(extra.get("context_signature", "")),
                        str(extra.get("strategy_signature", "")),
                        str(extra.get("diversity_tag", "")),
                        now_str(),
                    ),
                )
                audit_action(self.conn, int(mem_id), "move", "raw", "gold", float(score), flags)
                n_gold += 1
            elif target == "quarantine":
                self.conn.execute(
                    """
                    INSERT INTO memoria_jogos_quarantine(
                        source_memoria_id, concurso_ref, tipo_jogo, dezenas_json, hit, quality_score, reason_flags, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(mem_id),
                        int(concurso_ref),
                        int(tipo_jogo),
                        dezenas_json,
                        int(acertos),
                        float(score),
                        json.dumps(flags, ensure_ascii=False),
                        now_str(),
                    ),
                )
                audit_action(self.conn, int(mem_id), "move", "raw", "quarantine", float(score), flags)
                n_quar += 1
            else:
                audit_action(self.conn, int(mem_id), "ignore", "raw", "raw", float(score), flags)
                n_ign += 1

            max_id = max(max_id, int(mem_id))

        self._set_last_id(max_id)
        self.conn.commit()

        compress_stats = {"kept": 0, "removed": 0}
        if bool(self.cfg.get("enabled", True)):
            compress_stats = compress_gold(self.conn, self.cfg)

        return {
            "processed": len(rows),
            "gold": n_gold,
            "quarantine": n_quar,
            "ignored": n_ign,
            "last_id": max_id,
            "compress": compress_stats,
        }
