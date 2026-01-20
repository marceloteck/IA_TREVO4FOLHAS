# training/brains/statistical/freq_recente_brain.py
from __future__ import annotations

from collections import Counter, deque
from typing import Any, Dict, List, Optional
import random

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement


class StatFreqRecenteBrain(BaseBrain):
    """
    Cérebro Estatístico: Frequência Recente (janela móvel)
    - Aprende com resultado N+1 (incremental)
    - Mantém um buffer (deque) com os últimos X resultados
    - Gera jogos com foco nas dezenas mais frequentes na janela
    - Persiste estado no banco via BaseBrain (cerebro_estado JSON)
    """

    def __init__(self, db_conn, janela: int = 120, version: str = "v2"):
        super().__init__(
            db_conn=db_conn,
            brain_id=f"stat_freq_recente_{int(janela)}",
            name=f"Stat - Frequência Recente (janela={int(janela)})",
            category="estatistico",
            version=version,
        )

        self.janela = int(janela)
        self.buffer: deque[List[int]] = deque(maxlen=self.janela)
        self.freq: Counter[int] = Counter()

        # tenta carregar estado persistido
        self.load_state()
        self._rebuild_from_state()

    # ==========================
    # INTERFACE (BrainInterface)
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # quanto mais cheio o buffer, mais confiável
        if not self.buffer:
            return 0.55
        fill = len(self.buffer) / float(self.janela)
        return 0.70 + 0.30 * min(1.0, fill)

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)

        if size not in (15, 18):
            size = 15

        # Core mais “concentrado” para 15; mais amplo para 18
        core_size = 16 if size == 15 else 20

        # ranqueia por frequência recente
        ranked = sorted(UNIVERSO, key=lambda d: self.freq.get(d, 0), reverse=True)
        core = ranked[:core_size] if ranked else UNIVERSO[:]

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set()

            # parte 1: pega ~60% do jogo do core (ponderado)
            k_core = max(0, min(len(core), int(round(size * 0.60))))
            if k_core > 0:
                weights = {d: float(self.freq.get(d, 0) + 1.0) for d in core}
                picks = weighted_sample_without_replacement(weights, k_core)
                jogo.update(picks)

            # parte 2: completa com exploração controlada
            # (mistura universo + um pouco do core de novo)
            while len(jogo) < size:
                if random.random() < 0.65 and core:
                    jogo.add(random.choice(core))
                else:
                    jogo.add(random.choice(UNIVERSO))

            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0
        if not self.freq:
            return 0.1

        maxf = max(self.freq.values()) if self.freq else 1
        # score médio normalizado 0..1
        s = 0.0
        for d in jogo:
            s += float(self.freq.get(int(d), 0)) / float(maxf)
        return s / float(len(jogo))

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        # aprendizado incremental deve usar resultado real N+1
        if not resultado_n1:
            return

        novo = [int(x) for x in resultado_n1]

        # se buffer cheio, remove contribuição do mais antigo
        if len(self.buffer) == self.buffer.maxlen:
            old = self.buffer[0]
            self.freq.subtract(old)
            # remove chaves zeradas/negativas
            for k in list(self.freq.keys()):
                if self.freq[k] <= 0:
                    del self.freq[k]

        self.buffer.append(novo)
        self.freq.update(novo)

        # registra performance por concurso (leve) — usa BaseBrain
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # PERSISTÊNCIA (BaseBrain usa self.state)
    # ==========================
    def save_state(self) -> None:
        # armazena o mínimo para reconstruir
        self.state = {
            "janela": int(self.janela),
            "buffer": [list(map(int, r)) for r in self.buffer],
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()
        # não reconstrói aqui direto; reconstrói em _rebuild_from_state

    # ==========================
    # HELPERS
    # ==========================
    def _rebuild_from_state(self) -> None:
        """
        Reconstrói buffer/freq a partir do self.state.
        """
        try:
            janela = int(self.state.get("janela", self.janela))
            buff = self.state.get("buffer", []) or []
            buff = [list(map(int, r)) for r in buff if r]

            self.janela = max(10, janela)
            self.buffer = deque(buff[-self.janela :], maxlen=self.janela)

            self.freq = Counter()
            for r in self.buffer:
                self.freq.update(r)
        except Exception:
            # fallback seguro
            self.buffer = deque(maxlen=self.janela)
            self.freq = Counter()

    def report(self) -> Dict[str, Any]:
        ranked = sorted(UNIVERSO, key=lambda d: self.freq.get(d, 0), reverse=True)
        top10 = ranked[:10]
        return {
            **super().report(),
            "janela": int(self.janela),
            "buffer_len": int(len(self.buffer)),
            "top10": top10,
        }
