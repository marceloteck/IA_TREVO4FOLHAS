from __future__ import annotations

import random
import sqlite3


class BaselineGenerator:
    def __init__(self, db_conn, cfg: dict):
        self.conn: sqlite3.Connection = db_conn
        self.cfg = dict(cfg or {})

    def _fetch_rows(self, concurso_ref: int, recent_window: int | None = None) -> list[list[int]]:
        if recent_window is None:
            rows = self.conn.execute(
                """
                SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
                FROM concursos WHERE concurso <= ? ORDER BY concurso ASC
                """,
                (int(concurso_ref),),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
                FROM concursos WHERE concurso <= ? ORDER BY concurso DESC LIMIT ?
                """,
                (int(concurso_ref), int(recent_window)),
            ).fetchall()
        return [[int(x) for x in r] for r in rows]

    def _freq(self, rows: list[list[int]]) -> dict[int, float]:
        f = {i: 0.0 for i in range(1, 26)}
        for r in rows:
            for d in r:
                f[int(d)] += 1.0
        total = max(1.0, sum(f.values()))
        return {k: v / total for k, v in f.items()}

    def _generate_with_freq(self, freq: dict[int, float], tipo_jogo: int, max_games: int) -> list[list[int]]:
        quota_even = {7, 8, 9} if int(tipo_jogo) == 15 else {8, 9, 10}
        selected = []
        keys = sorted(freq.keys(), key=lambda d: freq[d], reverse=True)
        for i in range(int(max_games) * 4):
            top = keys[:15]
            sample = sorted(set(random.sample(top + random.sample(keys[15:], k=min(10, len(keys) - 15)), int(tipo_jogo))))
            if len(sample) != int(tipo_jogo):
                continue
            even = sum(1 for d in sample if d % 2 == 0)
            if even not in quota_even:
                continue
            if any(len(set(sample) & set(s)) / float(len(set(sample) | set(s))) > 0.78 for s in selected):
                continue
            selected.append(sample)
            if len(selected) >= int(max_games):
                break
        return selected

    def generate(self, concurso_ref: int, tipo_jogo: int, max_games: int, variant: str) -> list[list[int]]:
        if str(variant) == "recent_120":
            rows = self._fetch_rows(concurso_ref, recent_window=120)
        else:
            rows = self._fetch_rows(concurso_ref, recent_window=None)
        freq = self._freq(rows)
        return self._generate_with_freq(freq, int(tipo_jogo), int(max_games))
