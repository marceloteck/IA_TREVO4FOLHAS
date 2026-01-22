# training/core/brain_hub.py
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Dict, List, Tuple

from training.core.brain_interface import BrainInterface

def jaccard(a: List[int], b: List[int]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0

class BrainHub:
    """
    BrainHub (linha única):
    - seleciona cérebros por relevância
    - coleta candidatos
    - rankeia por score combinado
    - aplica diversidade (anti-colapso)
    - aprende atribuindo crédito ao cérebro de origem
    """

    def __init__(self, db_conn, exploration_rate: float = 0.08, max_brain_share: float = 0.4):
        self.db = db_conn
        self.brains: List[BrainInterface] = []
        self.meta = defaultdict(lambda: {"usos": 0, "pontos": 0, "q14": 0, "q15": 0})
        self.exploration_rate = max(0.0, min(0.25, float(exploration_rate)))
        self.max_brain_share = max(0.1, min(0.7, float(max_brain_share)))

    def _meta_weight(self, brain_id: str) -> float:
        meta = self.meta.get(brain_id)
        if not meta:
            return 1.0
        usos = max(1, int(meta.get("usos", 0)))
        pontos = float(meta.get("pontos", 0))
        q14 = int(meta.get("q14", 0))
        q15 = int(meta.get("q15", 0))

        media = pontos / float(usos)
        bonus = (q14 * 0.6 + q15 * 1.2) / float(usos)
        peso = 1.0 + (media / 15.0) * 0.15 + bonus * 0.25
        return max(0.85, min(1.25, peso))

    def register(self, brain: BrainInterface) -> None:
        self.brains.append(brain)

    def load_all(self) -> None:
        for b in self.brains:
            b.load_state()

    def save_all(self) -> None:
        for b in self.brains:
            b.save_state()

    def generate_candidates(self, context: Dict[str, Any], size: int, per_brain: int) -> List[Dict[str, Any]]:
        cand: List[Dict[str, Any]] = []
        raw_scores: Dict[str, List[float]] = defaultdict(list)

        for b in self.brains:
            if not getattr(b, "enabled", True):
                continue
            rel = float(b.evaluate_context(context))
            if rel <= 0:
                continue
            jogos = b.generate(context=context, size=size, n=per_brain)
            for j in jogos:
                raw = float(b.score_game(j, context))
                raw_scores[b.id].append(raw)
                cand.append(
                    {
                        "jogo": sorted(j),
                        "score_raw": raw,
                        "brain_id": b.id,
                        "rel": rel,
                    }
                )

        if not cand:
            return []

        score_bounds = {
            brain_id: (min(scores), max(scores)) for brain_id, scores in raw_scores.items()
        }

        for c in cand:
            min_s, max_s = score_bounds[c["brain_id"]]
            if max_s > min_s:
                norm = (c["score_raw"] - min_s) / (max_s - min_s)
            else:
                norm = 0.5

            meta_weight = self._meta_weight(c["brain_id"])
            calibrated = (norm * 0.65 + c["rel"] * 0.35) * meta_weight
            noise = random.uniform(0.0, self.exploration_rate)
            c["score"] = calibrated * (1.0 - self.exploration_rate) + noise

        return cand

    def diversify(
        self,
        candidatos: List[Dict[str, Any]],
        top_n: int,
        max_sim: float,
        max_per_brain: int,
    ) -> List[Dict[str, Any]]:
        candidatos.sort(key=lambda x: x["score"], reverse=True)
        escolhidos: List[Dict[str, Any]] = []
        brain_counts: Dict[str, int] = defaultdict(int)

        def pick_with_threshold(threshold: float) -> None:
            for c in candidatos:
                if len(escolhidos) >= top_n:
                    break
                if brain_counts[c["brain_id"]] >= max_per_brain:
                    continue
                jogo = c["jogo"]
                ok = True
                for e in escolhidos:
                    if jaccard(jogo, e["jogo"]) >= threshold:
                        ok = False
                        break
                if ok:
                    escolhidos.append(c)
                    brain_counts[c["brain_id"]] += 1

        pick_with_threshold(max_sim)

        relax = max_sim
        while len(escolhidos) < top_n and relax < 0.98:
            relax = min(0.98, relax + 0.03)
            pick_with_threshold(relax)

        return escolhidos[:top_n]

    def generate_games(self, context: Dict[str, Any], size: int, per_brain: int, top_n: int) -> List[Dict[str, Any]]:
        candidatos = self.generate_candidates(context, size, per_brain)
        # diversidade mais rígida para 15, mais leve para 18
        max_sim = 0.80 if size == 15 else 0.88
        densidade = len(candidatos) / max(1, top_n)
        if densidade < 2.0:
            max_sim = min(0.95, max_sim + 0.05)
        share = self.max_brain_share if size == 15 else min(0.5, self.max_brain_share + 0.1)
        max_per_brain = max(2, int(top_n * share))
        return self.diversify(
            candidatos,
            top_n=top_n,
            max_sim=max_sim,
            max_per_brain=max_per_brain,
        )

    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any], brain_id: str):
        # meta-score do hub
        m = self.meta[brain_id]
        m["usos"] += 1
        m["pontos"] += pontos
        if pontos >= 14: m["q14"] += 1
        if pontos >= 15: m["q15"] += 1

        for b in self.brains:
            if b.id == brain_id:
                b.learn(concurso_n, jogo, resultado_n1, pontos, context)
                break
