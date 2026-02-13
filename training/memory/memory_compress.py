from __future__ import annotations

import json
import sqlite3

from training.meta.diversity import jaccard


def compress_gold(db_conn: sqlite3.Connection, cfg: dict) -> dict:
    clone_threshold = float(cfg.get("clone_threshold", 0.78))
    max_gold_size = int(cfg.get("max_gold_size", 250000))
    mode = str(cfg.get("compress_mode", "delete_redundant"))

    rows = db_conn.execute(
        """
        SELECT id, dezenas_json, hit, quality_score, context_signature
        FROM memoria_jogos_gold
        ORDER BY hit DESC, quality_score DESC, id ASC
        """
    ).fetchall()

    keep_ids: list[int] = []
    keep_sets: list[set[int]] = []
    seen_json = set()
    seen_context = {}
    removed = 0

    for row_id, dezenas_json, hit, quality_score, context_sig in rows:
        dezenas = sorted(set(json.loads(dezenas_json or "[]")))
        s = set(int(x) for x in dezenas)
        raw_key = tuple(dezenas)

        if int(hit) >= 14:
            keep_ids.append(int(row_id))
            keep_sets.append(s)
            seen_json.add(raw_key)
            seen_context[context_sig] = seen_context.get(context_sig, 0) + 1
            continue

        if raw_key in seen_json:
            removed += 1
            continue

        if seen_context.get(context_sig, 0) >= 30:
            removed += 1
            continue

        is_clone = any(jaccard(s, ks) > clone_threshold for ks in keep_sets[-400:])
        if is_clone:
            removed += 1
            continue

        keep_ids.append(int(row_id))
        keep_sets.append(s)
        seen_json.add(raw_key)
        seen_context[context_sig] = seen_context.get(context_sig, 0) + 1

        if len(keep_ids) >= max_gold_size:
            break

    if mode == "delete_redundant":
        to_delete = [int(r[0]) for r in rows if int(r[0]) not in set(keep_ids)]
        if to_delete:
            db_conn.executemany("DELETE FROM memoria_jogos_gold WHERE id=?", [(x,) for x in to_delete])
            db_conn.commit()

    return {"kept": len(keep_ids), "removed": removed, "max_gold_size": max_gold_size}
