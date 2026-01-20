# training/brains/temporal/atraso_brain.py
from __future__ import annotations

from typing import Any, Dict, List
import random

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement


class TemporalAtrasoBrain(BaseBrain):
    """
    Cérebro Temporal: Atraso (tempo desde a última aparição)
    - Aprende com resultado real N+1
    - Mantém last_seen[dezena] = último concurso em que apareceu
    - Gera jogos puxando dezenas mais "atrasadas" + exploração controlada
    - Persistência via BaseBrain (cerebro_estado JSON)
    """

    def __init__(self, db_conn, version: str = "v2"):
        super().__init__(
            db_conn=db_conn,
            brain_id="temporal_atraso",
            name="Temporal - Atraso (last_seen)",
            category="temporal",
            version=version,
        )

        # concurso onde cada dezena apareceu por último
        self.last_seen: Dict[int, int] = {d: 0 for d in UNIVERSO}
        self.ultimo_concurso_visto: int = 0

        self.load_state()
        self._rebuild_from_state()

    # ==========================
    # INTERFACE (BrainInterface)
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        """
        Em geral é útil sempre, mas ganha relevância quando:
        - o sistema está em “estagnação” (context pode indicar)
        - queremos diversidade
        """
        return 0.85 if self.ultimo_concurso_visto > 0 else 0.70

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18):
            size = 15

        concurso_ref = int(context.get("concurso_n", self.ultimo_concurso_visto or 0))
        if concurso_ref <= 0:
            concurso_ref = self.ultimo_concurso_visto or 1

        # atraso = concurso_ref - last_seen
        atrasos = {d: max(0, concurso_ref - int(self.last_seen.get(d, 0))) for d in UNIVERSO}
        ranked = sorted(UNIVERSO, key=lambda d: atrasos[d], reverse=True)

        # core de atrasadas
        core_size = 16 if size == 15 else 20
        core = ranked[:core_size] if ranked else UNIVERSO[:]

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set()

            # pega ~50% do jogo do core (ponderado por atraso)
            k_core = max(0, min(len(core), int(round(size * 0.50))))
            if k_core > 0:
                weights = {d: float(atrasos.get(d, 0) + 1.0) for d in core}
                picks = weighted_sample_without_replacement(weights, k_core)
                jogo.update(picks)

            # completa com mistura: parte universo, parte core (diversidade)
            while len(jogo) < size:
                if random.random() < 0.55 and core:
                    jogo.add(random.choice(core))
                else:
                    jogo.add(random.choice(UNIVERSO))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        """
        Score comparativo: média do atraso das dezenas do jogo.
        Normalização leve para não explodir.
        """
        if not jogo:
            return 0.0

        concurso_ref = int(context.get("concurso_n", self.ultimo_concurso_visto or 0))
        if concurso_ref <= 0:
            concurso_ref = self.ultimo_concurso_visto or 1

        s = 0.0
        for d in jogo:
            s += float(max(0, concurso_ref - int(self.last_seen.get(int(d), 0))))

        # normalização simples: divide por um fator fixo
        return s / (float(len(jogo)) * 25.0)

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        """
        Atualiza com o concurso N+1 (resultado real).
        """
        if not resultado_n1:
            return

        concurso_n1 = int(concurso_n) + 1
        for d in resultado_n1:
            self.last_seen[int(d)] = concurso_n1

        if concurso_n1 > self.ultimo_concurso_visto:
            self.ultimo_concurso_visto = concurso_n1

        # registra performance por concurso (leve)
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # PERSISTÊNCIA (BaseBrain)
    # ==========================
    def save_state(self) -> None:
        self.state = {
            "ultimo_concurso_visto": int(self.ultimo_concurso_visto),
            "last_seen": {str(k): int(v) for k, v in self.last_seen.items()},
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

    # ==========================
    # HELPERS
    # ==========================
    def _rebuild_from_state(self) -> None:
        try:
            self.ultimo_concurso_visto = int(self.state.get("ultimo_concurso_visto", self.ultimo_concurso_visto))
            raw = self.state.get("last_seen", {}) or {}
            self.last_seen = {int(k): int(v) for k, v in raw.items()}

            # garante universo completo
            for d in UNIVERSO:
                if d not in self.last_seen:
                    self.last_seen[d] = 0
        except Exception:
            self.ultimo_concurso_visto = 0
            self.last_seen = {d: 0 for d in UNIVERSO}

    def report(self) -> Dict[str, Any]:
        concurso_ref = self.ultimo_concurso_visto or 0
        atrasos = {d: max(0, concurso_ref - int(self.last_seen.get(d, 0))) for d in UNIVERSO}
        ranked = sorted(UNIVERSO, key=lambda d: atrasos[d], reverse=True)
        return {
            **super().report(),
            "ultimo_concurso_visto": int(self.ultimo_concurso_visto),
            "top10_atrasadas": ranked[:10],
        }
