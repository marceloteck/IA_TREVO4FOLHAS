from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from training.brains._utils import UNIVERSO, weighted_sample_without_replacement
from training.core.base_brain import BaseBrain


class StructuralCoreProtectBrain(BaseBrain):
    """
    Cérebro estrutural focado em proteger um núcleo crítico.
    - Aprende coocorrências fortes no histórico recente.
    - Gera jogos garantindo presença mínima do núcleo.
    - Penaliza ausência de blocos críticos que derrubam pontuação.
    """

    def __init__(
        self,
        db_conn,
        core_size: int = 5,
        required_in_core: int = 4,
        janela_recente: int = 200,
        max_blocks: int = 30,
    ):
        super().__init__(
            db_conn=db_conn,
            brain_id="struct_core_protect",
            name="Structural - Core Protect",
            category="estrutural",
            version="v1",
        )
        self.core_size = int(core_size)
        self.required_in_core = int(required_in_core)
        self.janela_recente = int(janela_recente)
        self.max_blocks = int(max_blocks)

        self.state = self.state or {
            "core_seed": [6, 7, 12, 18, 23],
            "block_penalties": {},
        }

    def evaluate_context(self, context: Dict[str, Any]) -> float:
        historico = context.get("historico_recente") or []
        if len(historico) >= 120:
            return 0.95
        if len(historico) >= 60:
            return 0.85
        return 0.7

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        core = self._build_core(context)
        required = min(self.required_in_core, len(core), size)
        weights = self._frequency_weights(context)

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set(core[:required])
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
        core = self._build_core(context)
        required = min(self.required_in_core, len(core), len(jogo))
        core_hits = len(set(jogo) & set(core))
        if core_hits < required:
            return 0.05

        base = core_hits / max(1, len(core))
        penalty = self._penalty_for_missing_blocks(jogo)
        return max(0.0, min(1.0, base - penalty))

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        if not resultado_n1 or not jogo:
            return
        core = self._build_core(context)
        missing_core = len(set(core) - set(jogo))

        block_penalties = self.state.get("block_penalties", {})
        if missing_core >= 2 and pontos <= 11:
            blocks = self._extract_blocks(core, sizes=(2, 3))
            for block in blocks:
                key = ",".join(map(str, block))
                block_penalties[key] = block_penalties.get(key, 0.0) + 0.1

        self.state["block_penalties"] = block_penalties
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    def _build_core(self, context: Dict[str, Any]) -> List[int]:
        historico = context.get("historico_recente") or []
        recent = historico[-self.janela_recente :] if historico else []
        coocc = Counter()
        freq = Counter()
        for jogo in recent:
            freq.update(jogo)
            for i in range(len(jogo)):
                for j in range(i + 1, len(jogo)):
                    key = tuple(sorted((jogo[i], jogo[j])))
                    coocc[key] += 1

        if not freq:
            return list(self.state.get("core_seed", []))[: self.core_size]

        ranked = sorted(coocc.items(), key=lambda x: x[1], reverse=True)[: self.max_blocks]
        score_map = defaultdict(int)
        for (a, b), score in ranked:
            score_map[a] += score
            score_map[b] += score

        core_sorted = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
        core = [d for d, _ in core_sorted][: self.core_size]
        if len(core) < self.core_size:
            extras = [d for d, _ in freq.most_common() if d not in core]
            core.extend(extras[: self.core_size - len(core)])
        return core

    def _frequency_weights(self, context: Dict[str, Any]) -> Dict[int, float]:
        freq = context.get("freq_recente") or {}
        weights = {d: float(freq.get(d, 0)) + 1.0 for d in UNIVERSO}
        return weights

    def _extract_blocks(self, core: List[int], sizes: Tuple[int, ...]) -> List[Tuple[int, ...]]:
        blocks: List[Tuple[int, ...]] = []
        for size in sizes:
            if size <= 0 or size > len(core):
                continue
            for i in range(len(core) - size + 1):
                block = tuple(sorted(core[i : i + size]))
                blocks.append(block)
        return blocks

    def _penalty_for_missing_blocks(self, jogo: List[int]) -> float:
        penalties = self.state.get("block_penalties", {})
        if not penalties:
            return 0.0
        jogo_set = set(jogo)
        total = 0.0
        for key, value in penalties.items():
            block = {int(x) for x in key.split(",") if x}
            if block and not block.issubset(jogo_set):
                total += float(value)
        return min(0.5, total)
