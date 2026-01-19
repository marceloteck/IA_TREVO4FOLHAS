# training/core/brain_hub.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from collections import defaultdict
import random

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

    def __init__(self, db_conn):
        self.db = db_conn
        self.brains: List[BrainInterface] = []
        self.meta = defaultdict(lambda: {"usos": 0, "pontos": 0, "q14": 0, "q15": 0})

    def register(self, brain: BrainInterface) -> None:
        self.brains.append(brain)

    def load_all(self) -> None:
        for b in self.brains:
            b.load_state()

    def save_all(self) -> None:
        for b in self.brains:
            b.save_state()

    def generate_candidates(self, context: Dict[str, Any], size: int, per_brain: int) -> List[Dict[str, Any]]:
        cand = []
        for b in self.brains:
            if not getattr(b, "enabled", True):
                continue
            rel = float(b.evaluate_context(context))
            if rel <= 0:
                continue
            jogos = b.generate(context=context, size=size, n=per_brain)
            for j in jogos:
                s = float(b.score_game(j, context)) * 0.75 + rel * 0.25
                cand.append({"jogo": sorted(j), "score": s, "brain_id": b.id, "rel": rel})
        return cand

    def diversify(self, candidatos: List[Dict[str, Any]], top_n: int, max_sim: float) -> List[Dict[str, Any]]:
        candidatos.sort(key=lambda x: x["score"], reverse=True)
        escolhidos: List[Dict[str, Any]] = []
        for c in candidatos:
            jogo = c["jogo"]
            ok = True
            for e in escolhidos:
                if jaccard(jogo, e["jogo"]) >= max_sim:
                    ok = False
                    break
            if ok:
                escolhidos.append(c)
            if len(escolhidos) >= top_n:
                break
        return escolhidos

    def generate_games(self, context: Dict[str, Any], size: int, per_brain: int, top_n: int) -> List[Dict[str, Any]]:
        candidatos = self.generate_candidates(context, size, per_brain)
        # diversidade mais rígida para 15, mais leve para 18
        max_sim = 0.80 if size == 15 else 0.88
        return self.diversify(candidatos, top_n=top_n, max_sim=max_sim)

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
