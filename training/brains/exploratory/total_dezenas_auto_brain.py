# training/brains/exploratory/total_dezenas_auto_brain.py
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement, count_even, max_consecutive_run


class ExplorTotalDezenasAutoBrain(BaseBrain):
    """
    Cérebro Exploratório: Total de Dezenas Automático (16..20)
    ---------------------------------------------------------
    Ideia (inspirada no seu motor antigo):
    - Em vez de sempre montar diretamente 15/18, ele monta uma "base" de tamanho variável (16..20).
    - Depois, "comprime" para o tamanho alvo (15 ou 18) com regras leves:
        * aproxima paridade alvo do contexto
        * evita sequência consecutiva muito grande
        * favorece dezenas quentes recentes (se disponível no contexto)
        * mantém diversidade (não colapsa)
    - Aprende incrementalmente ajustando quais tamanhos-base funcionam melhor em cada cenário.

    Estado persistido:
    - contagem de sucesso por tamanho-base
    - preferências por paridade e estabilidade
    """

    def __init__(
        self,
        db_conn,
        tamanhos_base: Optional[List[int]] = None,
        version: str = "v1",
    ):
        super().__init__(
            db_conn=db_conn,
            brain_id="expl_total_dezenas_auto",
            name="Expl - Total de Dezenas Auto (16..20)",
            category="exploratorio",
            version=version,
        )

        self.tamanhos_base = tamanhos_base or [16, 17, 18, 19, 20]

        # desempenho por tamanho-base (meta)
        self.size_stats: Counter[int] = Counter()       # usos
        self.size_good: Counter[int] = Counter()        # 11+
        self.size_elite: Counter[int] = Counter()       # 14+

        # preferências aprendidas
        self.pref_even_target = 7   # default para 15
        self.pref_run_max = 5       # default razoável

        self.load_state()
        self._rebuild_from_state()

    # ==========================
    # BrainInterface
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        """
        Esse brain é mais útil quando:
        - poucos cérebros ainda (bootstrapping)
        - quer diversidade
        - ou quando o histórico recente é curto
        """
        hist = context.get("historico_recente") or []
        if len(hist) < 30:
            return 0.95
        return 0.75

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18):
            size = 15

        # escolhe distribuição de tamanhos-base (aprendida)
        jogos: List[List[int]] = []
        for _ in range(n):
            base_size = self._choose_base_size(size)
            base = self._make_base(context=context, base_size=base_size)

            # comprime base para o tamanho final desejado
            final_game = self._compress_base(
                context=context,
                base=base,
                target_size=size
            )
            jogos.append(sorted(final_game))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        """
        Score leve: quanto melhor encaixa nas "regras suaves".
        """
        if not jogo:
            return 0.0

        # 1) paridade próxima do alvo
        target_even = self._target_even(context=context, size=len(jogo))
        ev = count_even(jogo)
        s_even = max(0.0, 1.0 - (abs(ev - target_even) / 7.0))

        # 2) penaliza sequência muito longa
        run = max_consecutive_run(jogo)
        s_run = 1.0 if run <= self.pref_run_max else max(0.0, 1.0 - ((run - self.pref_run_max) / 4.0))

        # 3) leve boost por quentes recentes se existir freq_recente no contexto
        freq = context.get("freq_recente") or {}
        if freq:
            mx = max(freq.values()) if freq else 1
            s_freq = sum((freq.get(int(d), 0) / mx) for d in jogo) / float(len(jogo))
        else:
            s_freq = 0.3

        score = 0.45 * s_even + 0.25 * s_run + 0.30 * s_freq
        return float(max(0.0, score))

    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        """
        Aprende meta:
        - atualiza preferências (paridade alvo e run_max) baseado no que deu bom
        - (observação) o brain não sabe o base_size do jogo final após compressão,
          então usa heurística: deduz "tamanho-base preferido" pelo histórico do contexto
          e pelo alvo final.
        """
        # meta update (bem leve)
        size_final = len(jogo)
        base_size_guess = self._last_base_size_from_context(context, size_final)

        if base_size_guess is not None:
            self.size_stats[base_size_guess] += 1
            if pontos >= 11:
                self.size_good[base_size_guess] += 1
            if pontos >= 14:
                self.size_elite[base_size_guess] += 1

        # ajusta paridade alvo lentamente quando tem 12+
        if pontos >= 12:
            ev = count_even(jogo)
            # moving average discreta
            self.pref_even_target = int(round(0.85 * self.pref_even_target + 0.15 * ev))

        # ajusta run_max quando tem 13+
        if pontos >= 13:
            run = max_consecutive_run(jogo)
            # preferir manter run controlado
            self.pref_run_max = int(max(4, min(7, round(0.9 * self.pref_run_max + 0.1 * run))))

        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # Persistência
    # ==========================
    def save_state(self) -> None:
        self.state = {
            "tamanhos_base": [int(x) for x in self.tamanhos_base],
            "size_stats": {str(k): int(v) for k, v in self.size_stats.items()},
            "size_good": {str(k): int(v) for k, v in self.size_good.items()},
            "size_elite": {str(k): int(v) for k, v in self.size_elite.items()},
            "pref_even_target": int(self.pref_even_target),
            "pref_run_max": int(self.pref_run_max),
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

    def report(self) -> Dict[str, Any]:
        # taxa 11+ por base
        taxas = {}
        for s in self.tamanhos_base:
            u = int(self.size_stats.get(s, 0))
            g = int(self.size_good.get(s, 0))
            e = int(self.size_elite.get(s, 0))
            taxas[str(s)] = {
                "usos": u,
                "taxa_11+": (g / u) if u else 0.0,
                "taxa_14+": (e / u) if u else 0.0,
            }

        return {
            **super().report(),
            "tamanhos_base": [int(x) for x in self.tamanhos_base],
            "pref_even_target": int(self.pref_even_target),
            "pref_run_max": int(self.pref_run_max),
            "taxas_por_tamanho_base": taxas,
        }

    # ==========================
    # Internos
    # ==========================
    def _rebuild_from_state(self) -> None:
        try:
            tb = self.state.get("tamanhos_base") or self.tamanhos_base
            self.tamanhos_base = [int(x) for x in tb]

            ss = self.state.get("size_stats") or {}
            sg = self.state.get("size_good") or {}
            se = self.state.get("size_elite") or {}

            self.size_stats = Counter({int(k): int(v) for k, v in ss.items()})
            self.size_good = Counter({int(k): int(v) for k, v in sg.items()})
            self.size_elite = Counter({int(k): int(v) for k, v in se.items()})

            self.pref_even_target = int(self.state.get("pref_even_target", self.pref_even_target))
            self.pref_run_max = int(self.state.get("pref_run_max", self.pref_run_max))
        except Exception:
            self.size_stats = Counter()
            self.size_good = Counter()
            self.size_elite = Counter()

    def _choose_base_size(self, final_size: int) -> int:
        """
        Escolhe tamanho-base com exploração/exploração:
        - se já tem histórico: escolhe pelo "score esperado" (taxa 11+ e 14+)
        - senão: aleatório
        """
        choices = [s for s in self.tamanhos_base if s >= final_size]
        if not choices:
            choices = self.tamanhos_base[:]

        # exploração
        if random.random() < 0.25 or not self.size_stats:
            return int(random.choice(choices))

        # exploração com pesos por performance
        weights = []
        for s in choices:
            u = float(self.size_stats.get(s, 0))
            g = float(self.size_good.get(s, 0))
            e = float(self.size_elite.get(s, 0))
            # score esperado: prioriza elite, mas não zera o resto
            w = 0.6 * ((g + 1.0) / (u + 3.0)) + 0.4 * ((e + 0.5) / (u + 6.0))
            weights.append(max(0.05, float(w)))
        return int(random.choices(choices, weights=weights, k=1)[0])

    def _make_base(self, context: Dict[str, Any], base_size: int) -> List[int]:
        """
        Monta base usando:
        - frequência recente do contexto (se existir)
        - universo
        """
        base_size = int(base_size)
        freq = context.get("freq_recente") or {}

        if freq:
            # pega top por frequência recente como pool principal
            ranked = sorted(UNIVERSO, key=lambda d: freq.get(d, 0), reverse=True)
            core = ranked[: min(22, max(14, base_size + 2))]
            weights = {d: float(freq.get(d, 0) + 1.0) for d in core}
            base = weighted_sample_without_replacement(weights, min(base_size, len(core)))
            if len(base) < base_size:
                rest = [d for d in UNIVERSO if d not in base]
                base += random.sample(rest, base_size - len(base))
            return sorted(set(base))[:base_size]

        # fallback: aleatório
        return sorted(random.sample(UNIVERSO, base_size))

    def _compress_base(self, context: Dict[str, Any], base: List[int], target_size: int) -> List[int]:
        """
        Reduz a base para target_size escolhendo quais manter:
        - favorece dezenas com freq_recente alta
        - mantém paridade perto do alvo
        - evita run muito alto
        """
        base = sorted(set(int(x) for x in base))
        target_size = int(target_size)
        if len(base) <= target_size:
            # completa se faltar
            if len(base) < target_size:
                rest = [d for d in UNIVERSO if d not in base]
                base += random.sample(rest, target_size - len(base))
            return sorted(set(base))[:target_size]

        freq = context.get("freq_recente") or {}
        target_even = self._target_even(context=context, size=target_size)

        # pontua cada dezena para decidir quais ficar
        def dez_score(d: int) -> float:
            s = 0.0
            if freq:
                mx = max(freq.values()) if freq else 1
                s += 0.65 * (freq.get(d, 0) / mx)
            # leve priorização por diversidade (não "colar" tudo no meio)
            s += 0.10 * (1.0 - abs(d - 13) / 12.0)
            # ruído controlado para exploração
            s += 0.12 * random.random()
            return s

        ranked = sorted(base, key=dez_score, reverse=True)

        # seleção com tentativa de bater paridade e limitar run
        best = None
        best_sc = -1.0

        # tenta algumas combinações leves (não explode CPU)
        tries = 28
        for _ in range(tries):
            # pega um pool top e sorteia sem reposição
            pool = ranked[: min(len(ranked), target_size + 5)]
            sample = set(random.sample(pool, target_size))

            # checa paridade
            ev = count_even(list(sample))
            pen_even = abs(ev - target_even)

            # checa run
            run = max_consecutive_run(list(sample))
            pen_run = max(0, run - self.pref_run_max)

            # score total
            sc = 0.0
            for d in sample:
                sc += dez_score(int(d))
            sc = sc / float(target_size)

            sc = sc - 0.10 * pen_even - 0.08 * pen_run
            if sc > best_sc:
                best_sc = sc
                best = sample

        if best is None:
            best = set(ranked[:target_size])

        final = sorted(best)
        # garante tamanho
        if len(final) < target_size:
            rest = [d for d in UNIVERSO if d not in final]
            final += random.sample(rest, target_size - len(final))
        return sorted(set(final))[:target_size]

    def _target_even(self, context: Dict[str, Any], size: int) -> int:
        """
        Target paridade:
        - usa preferência aprendida como base
        - ajusta leve com último resultado se existir
        """
        size = int(size)
        base = 7 if size == 15 else 9
        t = int(round(0.6 * base + 0.4 * self.pref_even_target))

        last = context.get("ultimo_resultado") or []
        if last:
            ev_last = count_even(last)
            # puxa um pouco para o que vem acontecendo
            t = int(round(0.75 * t + 0.25 * ev_last))

        # clamp
        return int(max(3, min(size - 3, t)))

    def _last_base_size_from_context(self, context: Dict[str, Any], final_size: int) -> Optional[int]:
        """
        Heurística simples: se final_size=15, preferir base 18;
        se 18, preferir 20. Serve só para meta-contagem.
        """
        if final_size == 15:
            return 18 if 18 in self.tamanhos_base else random.choice(self.tamanhos_base)
        if final_size == 18:
            return 20 if 20 in self.tamanhos_base else max(self.tamanhos_base)
        return None
