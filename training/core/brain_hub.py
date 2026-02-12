# training/core/brain_hub.py
from __future__ import annotations

from collections import defaultdict
import random
from typing import Any, Dict, List, Set, Tuple, Union

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

    def __init__(
        self,
        db_conn,
        exploration_rate: float = 0.08,
        max_brain_share: float = 0.4,
        high_hit_focus: float = 0.0,
        quota_enabled: bool = False,
        quota_max_per_brain: int = 0,
        consensus_enabled: bool = False,
        consensus_bonus: float = 0.0,
        consensus_min_votes: int = 2,
        strong_consensus_enabled: bool = False,
        strong_consensus_bonus: float = 0.0,
        collapse_penalty_enabled: bool = False,
        collapse_penalty: float = 0.0,
        collapse_votes_threshold: int = 5,
    ):
        self.db = db_conn
        self.brains: List[BrainInterface] = []
        self.meta = defaultdict(lambda: {"usos": 0, "pontos": 0, "q14": 0, "q15": 0})

        self.exploration_rate = max(0.0, min(0.25, float(exploration_rate)))
        self.max_brain_share = max(0.1, min(0.7, float(max_brain_share)))
        self.high_hit_focus = max(0.0, min(0.5, float(high_hit_focus)))

        self.quota_enabled = bool(quota_enabled)
        self.quota_max_per_brain = max(0, int(quota_max_per_brain))

        self.consensus_enabled = bool(consensus_enabled)
        self.consensus_bonus = max(0.0, float(consensus_bonus))
        self.consensus_min_votes = max(2, int(consensus_min_votes))
        self.strong_consensus_enabled = bool(strong_consensus_enabled)
        self.strong_consensus_bonus = max(0.0, float(strong_consensus_bonus))

        self.collapse_penalty_enabled = bool(collapse_penalty_enabled)
        self.collapse_penalty = max(0.0, float(collapse_penalty))
        self.collapse_votes_threshold = max(2, int(collapse_votes_threshold))

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

    def _high_hit_rate(self, brain_id: str) -> float:
        meta = self.meta.get(brain_id)
        if not meta:
            return 0.0

        usos = max(1, int(meta.get("usos", 0)))
        q14 = int(meta.get("q14", 0))
        q15 = int(meta.get("q15", 0))
        rate = (q14 + (2 * q15)) / float(usos)
        return max(0.0, min(1.0, rate))

    def register(self, brain: BrainInterface) -> None:
        self.brains.append(brain)

    def load_all(self) -> None:
        for b in self.brains:
            b.load_state()

    def save_all(self) -> None:
        for b in self.brains:
            b.save_state()

    def generate_candidates(self, context: Dict[str, Any], size: int, per_brain: Union[int, Dict[str, int]]) -> List[Dict[str, Any]]:
        cand: List[Dict[str, Any]] = []
        raw_scores: Dict[str, List[float]] = defaultdict(list)

        votes_map: Dict[Tuple[int, ...], Set[str]] = defaultdict(set)

        for b in self.brains:
            if not getattr(b, "enabled", True):
                continue

            rel = float(b.evaluate_context(context))
            if rel <= 0:
                continue

            n_for_brain = int(per_brain.get(str(b.id), 0)) if isinstance(per_brain, dict) else int(per_brain)
            if n_for_brain <= 0:
                continue

            jogos = b.generate(context=context, size=size, n=n_for_brain)
            for j in jogos:
                jogo_sorted = tuple(sorted(j))
                raw = float(b.score_game(j, context))
                raw_scores[b.id].append(raw)

                votes_map[jogo_sorted].add(b.id)

                cand.append(
                    {
                        "jogo": list(jogo_sorted),
                        "score_raw": raw,
                        "brain_id": b.id,
                        "rel": rel,
                    }
                )

        if not cand:
            return []

        score_bounds = {
            brain_id: (min(scores), max(scores))
            for brain_id, scores in raw_scores.items()
            if scores
        }

        for c in cand:
            min_s, max_s = score_bounds.get(c["brain_id"], (0.0, 0.0))
            if max_s > min_s:
                norm = (float(c["score_raw"]) - float(min_s)) / (float(max_s) - float(min_s))
            else:
                norm = 0.5

            meta_weight = self._meta_weight(str(c["brain_id"]))
            calibrated = (norm * 0.65 + float(c["rel"]) * 0.35) * meta_weight

            noise = random.uniform(0.0, self.exploration_rate)
            score = calibrated * (1.0 - self.exploration_rate) + noise

            if int(size) == 15 and self.high_hit_focus > 0.0:
                high_hit_rate = self._high_hit_rate(str(c["brain_id"]))
                score += float(self.high_hit_focus) * float(high_hit_rate)

            if self.consensus_enabled:
                votes = len(votes_map.get(tuple(c["jogo"]), set()))
                c["consensus_votes"] = votes
                if votes >= self.consensus_min_votes:
                    score += self.consensus_bonus

            if self.strong_consensus_enabled:
                votes = len(votes_map.get(tuple(c["jogo"]), set()))
                weighted_votes = sum(self._meta_weight(bid) for bid in votes_map.get(tuple(c["jogo"]), set()))
                c["consensus_weighted_votes"] = float(weighted_votes)
                score += self.strong_consensus_bonus * float(weighted_votes)

            if self.collapse_penalty_enabled:
                votes = len(votes_map.get(tuple(c["jogo"]), set()))
                if votes >= self.collapse_votes_threshold:
                    score -= self.collapse_penalty

            c["score"] = float(score)

        return cand

    def diversify(
        self,
        candidatos: List[Dict[str, Any]],
        top_n: int,
        max_sim: float,
        max_per_brain: int,
    ) -> List[Dict[str, Any]]:
        candidatos.sort(key=lambda x: float(x["score"]), reverse=True)
        escolhidos: List[Dict[str, Any]] = []
        brain_counts: Dict[str, int] = defaultdict(int)

        def pick_with_threshold(threshold: float) -> None:
            for c in candidatos:
                if len(escolhidos) >= top_n:
                    break

                bid = str(c["brain_id"])
                if brain_counts[bid] >= max_per_brain:
                    continue

                jogo = c["jogo"]
                ok = True
                for e in escolhidos:
                    if jaccard(jogo, e["jogo"]) >= threshold:
                        ok = False
                        break

                if ok:
                    escolhidos.append(c)
                    brain_counts[bid] += 1

        pick_with_threshold(float(max_sim))

        relax = float(max_sim)
        while len(escolhidos) < top_n and relax < 0.98:
            relax = min(0.98, relax + 0.03)
            pick_with_threshold(relax)

        return escolhidos[:top_n]

    def generate_games(self, context: Dict[str, Any], size: int, per_brain: Union[int, Dict[str, int]], top_n: int) -> List[Dict[str, Any]]:
        candidatos = self.generate_candidates(context, size, per_brain)

        # diversidade mais rígida para 15, mais leve para 18
        max_sim = 0.80 if int(size) == 15 else 0.88

        densidade = len(candidatos) / max(1, int(top_n))
        if densidade < 2.0:
            max_sim = min(0.95, max_sim + 0.05)

        share = self.max_brain_share if int(size) == 15 else min(0.5, self.max_brain_share + 0.1)
        max_per_brain = max(2, int(int(top_n) * float(share)))

        if self.quota_enabled and self.quota_max_per_brain > 0:
            max_per_brain = min(max_per_brain, int(self.quota_max_per_brain))

        return self.diversify(
            candidatos,
            top_n=int(top_n),
            max_sim=float(max_sim),
            max_per_brain=int(max_per_brain),
        )

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
        brain_id: str,
    ) -> None:
        m = self.meta[str(brain_id)]
        m["usos"] += 1
        m["pontos"] += int(pontos)
        if int(pontos) >= 14:
            m["q14"] += 1
        if int(pontos) >= 15:
            m["q15"] += 1

        for b in self.brains:
            if b.id == brain_id:
                b.learn(concurso_n, jogo, resultado_n1, pontos, context)
                break

    def learn_with_feedback(
        self,
        context: Dict[str, Any],
        candidatos: List[Dict[str, Any]],
        resultado_n1: List[int],
    ) -> None:
        """
        Aprende a partir de uma lista de candidatos avaliados no backtest.

        Espera candidatos no formato retornado por ``generate_games``.
        Método tolerante a registros incompletos para evitar quebrar ciclos longos.
        """
        concurso_n = int(context.get("concurso_n", 0) or 0)
        resultado_sorted = sorted(int(x) for x in (resultado_n1 or []) if x is not None)

        if concurso_n <= 0 or not resultado_sorted:
            return

        for cand in candidatos or []:
            brain_id = str(cand.get("brain_id", "")).strip()
            if not brain_id:
                continue

            jogo = sorted(set(int(x) for x in cand.get("jogo", []) if x is not None))
            if not jogo:
                continue

            pontos = len(set(jogo) & set(resultado_sorted))
            self.learn(
                concurso_n=concurso_n,
                jogo=jogo,
                resultado_n1=resultado_sorted,
                pontos=int(pontos),
                context=context,
                brain_id=brain_id,
            )
