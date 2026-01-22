from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from training.brains._utils import UNIVERSO, weighted_sample_without_replacement
from training.core.base_brain import BaseBrain


class StructuralAntiAbsenceBrain(BaseBrain):
    """
    Cérebro Anti-Ausência (CAA):
    - Mantém 2 núcleos fixos (A e B) e aprende um núcleo C dinâmico por coocorrência.
    - Calcula risco de ausência (RAN) e prioriza jogos que protegem os núcleos.
    """

    def __init__(
        self,
        db_conn,
        core_a: List[int] | None = None,
        core_b: List[int] | None = None,
        janela_recente: int = 120,
    ):
        super().__init__(
            db_conn=db_conn,
            brain_id="struct_anti_absence",
            name="Structural - Anti Absence",
            category="estrutural",
            version="v1",
        )
        self.core_a = core_a or [6, 7, 12, 18, 23]
        self.core_b = core_b or [1, 4, 5, 9, 13, 17, 20, 21, 22, 25]
        self.janela_recente = int(janela_recente)
        self.state = self.state or {"core_c": []}

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        historico = context.get("historico_recente") or []
        return 0.9 if len(historico) >= 60 else 0.7

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        core_c = self._build_core_c(context)
        freq = context.get("freq_recente") or {}
        weights = {d: float(freq.get(d, 0)) + 1.0 for d in UNIVERSO}

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set()
            jogo.update(self.core_a[: min(4, size)])
            jogo.update(self.core_b[: min(8, max(0, size - len(jogo)))])
            faltam = size - len(jogo)
            if faltam > 0:
                pool = {d: w for d, w in weights.items() if d not in jogo}
                if not pool:
                    pool = {d: 1.0 for d in UNIVERSO if d not in jogo}
                jogo.update(weighted_sample_without_replacement(pool, faltam))
            jogos.append(sorted(jogo))
        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        ran = self._risk_absence(jogo, context)
        return max(0.0, 1.0 - ran)

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        core_c = self._build_core_c(context)
        self.state["core_c"] = core_c
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    def _risk_absence(self, jogo: List[int], context: Dict[str, Any]) -> float:
        core_c = self._build_core_c(context)
        hit_a = len(set(jogo) & set(self.core_a))
        hit_b = len(set(jogo) & set(self.core_b))
        hit_c = len(set(jogo) & set(core_c))

        penalty = 0.0
        if hit_a < 4:
            penalty += 0.45
        if hit_b < 8:
            penalty += 0.30
        if hit_c < 3:
            penalty += 0.15
        return min(0.9, penalty)

    def _build_core_c(self, context: Dict[str, Any]) -> List[int]:
        historico = context.get("historico_recente") or []
        recent = historico[-self.janela_recente :] if historico else []
        coocc = Counter()
        for jogo in recent:
            for i in range(len(jogo)):
                for j in range(i + 1, len(jogo)):
                    key = tuple(sorted((jogo[i], jogo[j])))
                    coocc[key] += 1
        score_map = defaultdict(int)
        for (a, b), score in coocc.items():
            score_map[a] += score
            score_map[b] += score
        ranked = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
        core_c = [d for d, _ in ranked[:5]]
        return core_c
