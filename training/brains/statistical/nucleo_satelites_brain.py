# training/brains/statistical/nucleo_satelites_brain.py
from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Tuple, Optional

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement, count_even, max_consecutive_run


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


class StatNucleoSatelitesBrain(BaseBrain):
    """
    Cérebro Estatístico: Núcleo + Satélites (incremental e persistente)
    -------------------------------------------------------------------
    Ideia (evolução do seu motor antigo):
    - Aprende um "núcleo" de dezenas centrais (freq + coocorrência)
    - Aprende "satélites" que orbitam o núcleo (pares fortes com o núcleo)
    - Mantém um pequeno sinal de "elite" (jogos 14+) para reforçar padrões raros
    - Gera jogos misturando:
        1) núcleo (ex.: 4 dezenas)
        2) satélites (com pesos por coocorrência)
        3) reforço por elite_freq (se houver)
        4) completa com freq_recente do contexto e universo (exploração controlada)

    Performance:
    - Mantém Counter de freq e Counter de pares
    - Poda pares para não crescer infinito (top_k)
    - Estado salvo no SQLite via BaseBrain (cerebro_estado JSON)

    Observação:
    - Aprende usando resultado real N+1 (resultado_n1), que é a fonte "verdade"
      para padrões reais de sorteio.
    """

    def __init__(
        self,
        db_conn,
        top_pairs_keep: int = 600,
        version: str = "v1",
    ):
        super().__init__(
            db_conn=db_conn,
            brain_id="stat_nucleo_satelites",
            name="Stat - Núcleo + Satélites (coocorrência)",
            category="estatistico",
            version=version,
        )

        self.top_pairs_keep = int(max(200, min(5000, top_pairs_keep)))

        # memórias internas (leves)
        self.freq: Counter[int] = Counter()
        self.pairs: Counter[Tuple[int, int]] = Counter()
        self.elite_freq: Counter[int] = Counter()  # reforço quando acertos>=14
        self.learn_steps: int = 0

        # caches derivados
        self._cached_nucleo: List[int] = []
        self._cached_satelites: List[int] = []

        self.load_state()
        self._rebuild_from_state()
        self._recompute_core()

    # ==========================
    # BrainInterface
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # No início, é MUITO útil; depois estabiliza.
        # Se temos pouco aprendizado, sobe relevância.
        if self.learn_steps < 80:
            return 0.95
        return 0.80

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18):
            size = 15

        # garante cache pronto
        if not self._cached_nucleo or not self._cached_satelites:
            self._recompute_core()

        nucleo = list(self._cached_nucleo)
        sat = list(self._cached_satelites)

        # fallback se ainda estiver fraco
        if not nucleo:
            nucleo = UNIVERSO[:]
        if not sat:
            sat = UNIVERSO[:]

        # alvo de paridade pelo contexto
        target_even = self._target_even(context=context, size=size)

        freq_rec = context.get("freq_recente") or {}
        ranked_rec = sorted(UNIVERSO, key=lambda d: freq_rec.get(d, 0), reverse=True)
        top_rec = ranked_rec[:12] if ranked_rec else []

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set()

            # 1) núcleo (fixo pequeno)
            k_nucleo = 4 if size == 15 else 5
            k_nucleo = min(k_nucleo, len(nucleo))
            if k_nucleo > 0:
                jogo.update(random.sample(nucleo, k_nucleo))

            # 2) satélites ponderados por força com o núcleo
            #    quanto mais o satélite coocorre com o núcleo, mais peso.
            remaining = size - len(jogo)
            if remaining > 0:
                sat_pool = [d for d in sat if d not in jogo]
                sat_pool = sat_pool[: max(18, remaining + 8)]  # pool pequeno e eficiente

                weights: Dict[int, float] = {}
                for d in sat_pool:
                    w = 1.0
                    # peso por pares com o núcleo
                    for nn in jogo:
                        w += float(self.pairs.get(_pair_key(int(d), int(nn)), 0))
                    # reforço por elite
                    w += 0.35 * float(self.elite_freq.get(int(d), 0))
                    # reforço por recência
                    w += 0.25 * float(freq_rec.get(int(d), 0))
                    weights[int(d)] = w

                k_sat = max(0, min(len(sat_pool), int(round(size * 0.45))))
                k_sat = min(k_sat, remaining)
                if k_sat > 0:
                    picks = weighted_sample_without_replacement(weights, k_sat)
                    jogo.update(picks)

            # 3) reforço por dezenas "elite"
            remaining = size - len(jogo)
            if remaining > 0 and self.elite_freq:
                elite_rank = sorted(UNIVERSO, key=lambda d: self.elite_freq.get(d, 0), reverse=True)
                elite_pool = [d for d in elite_rank[:14] if d not in jogo]
                if elite_pool:
                    take = min(remaining, max(0, int(round(size * 0.20))))
                    take = min(take, len(elite_pool))
                    if take > 0:
                        jogo.update(random.sample(elite_pool, take))

            # 4) completa com recência/top e universo (exploração controlada)
            while len(jogo) < size:
                if top_rec and random.random() < 0.60:
                    jogo.add(random.choice(top_rec))
                elif sat and random.random() < 0.25:
                    jogo.add(random.choice(sat))
                else:
                    jogo.add(random.choice(UNIVERSO))

            # 5) ajuste leve para paridade/run (sem explosão de custo)
            jogo = self._polish_game(list(jogo), size=size, target_even=target_even, context=context)
            jogos.append(sorted(jogo))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0

        nucleo = set(self._cached_nucleo or [])
        sat = set(self._cached_satelites or [])

        # 1) presença em núcleo e satélites
        in_nuc = sum(1 for d in jogo if int(d) in nucleo)
        in_sat = sum(1 for d in jogo if int(d) in sat)

        s_core = (in_nuc / 5.0) * 0.60 + (in_sat / float(len(jogo))) * 0.40
        s_core = max(0.0, min(1.0, s_core))

        # 2) pares fortes internos (normalizado)
        ps = 0.0
        for i in range(len(jogo)):
            for j in range(i + 1, len(jogo)):
                ps += float(self.pairs.get(_pair_key(int(jogo[i]), int(jogo[j])), 0))
        ps = ps / 300.0  # escala comparativa

        # 3) elite boost
        if self.elite_freq:
            mx = max(self.elite_freq.values())
            elite_s = sum((self.elite_freq.get(int(d), 0) / mx) for d in jogo) / float(len(jogo))
        else:
            elite_s = 0.15

        # 4) penaliza run exagerado
        run = max_consecutive_run(jogo)
        pen_run = max(0.0, (run - 6) / 6.0)

        score = 0.45 * s_core + 0.25 * elite_s + 0.30 * min(1.0, ps) - 0.12 * pen_run
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
        Aprendizado incremental N -> N+1:
        - Atualiza freq/pairs usando resultado real N+1 (fonte)
        - Se pontos>=14: reforça elite_freq pelo jogo que quase bateu 15
        - Poda pares para manter leve
        """
        if not resultado_n1:
            return

        res = [int(x) for x in resultado_n1]
        res_set = sorted(set(res))

        # 1) freq
        self.freq.update(res_set)

        # 2) pares do resultado real
        for i in range(len(res_set)):
            for j in range(i + 1, len(res_set)):
                self.pairs[_pair_key(res_set[i], res_set[j])] += 1

        # 3) sinal elite (quando quase acertou)
        if int(pontos) >= 14 and jogo:
            for d in set(int(x) for x in jogo):
                self.elite_freq[d] += 1

        self.learn_steps += 1

        # 4) poda periódica (não crescer infinito)
        if self.learn_steps % 60 == 0:
            self._prune_pairs()

        # 5) atualiza núcleo/satélites periodicamente
        if self.learn_steps % 25 == 0:
            self._recompute_core()

        # 6) performance leve
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # Persistência
    # ==========================
    def save_state(self) -> None:
        # salva pouco e suficiente
        pairs_top = self.pairs.most_common(self.top_pairs_keep)

        self.state = {
            "top_pairs_keep": int(self.top_pairs_keep),
            "learn_steps": int(self.learn_steps),
            "freq": {str(k): int(v) for k, v in self.freq.items()},
            "elite_freq": {str(k): int(v) for k, v in self.elite_freq.items()},
            "pairs": [[int(a), int(b), int(c)] for (a, b), c in pairs_top],
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

    def report(self) -> Dict[str, Any]:
        return {
            **super().report(),
            "learn_steps": int(self.learn_steps),
            "nucleo": list(self._cached_nucleo[:10]),
            "satelites": list(self._cached_satelites[:15]),
            "pairs_kept": int(len(self.pairs)),
            "elite_top": [d for d, _ in self.elite_freq.most_common(8)],
        }

    # ==========================
    # Internos
    # ==========================
    def _rebuild_from_state(self) -> None:
        try:
            self.top_pairs_keep = int(self.state.get("top_pairs_keep", self.top_pairs_keep))
            self.learn_steps = int(self.state.get("learn_steps", 0))

            rf = self.state.get("freq") or {}
            self.freq = Counter({int(k): int(v) for k, v in rf.items()})

            ef = self.state.get("elite_freq") or {}
            self.elite_freq = Counter({int(k): int(v) for k, v in ef.items()})

            rp = self.state.get("pairs") or []
            self.pairs = Counter()
            for a, b, c in rp:
                self.pairs[_pair_key(int(a), int(b))] = int(c)
        except Exception:
            self.freq = Counter()
            self.pairs = Counter()
            self.elite_freq = Counter()
            self.learn_steps = 0

    def _prune_pairs(self) -> None:
        if len(self.pairs) <= self.top_pairs_keep:
            return
        self.pairs = Counter(dict(self.pairs.most_common(self.top_pairs_keep)))

    def _recompute_core(self) -> None:
        """
        Núcleo = dezenas mais "centrais" (freq + força de pares).
        Satélites = dezenas que mais se conectam ao núcleo.
        """
        if not self.freq:
            self._cached_nucleo = []
            self._cached_satelites = []
            return

        # centralidade aproximada: freq + soma dos pares envolvendo a dezena
        pair_strength = {d: 0 for d in UNIVERSO}
        for (a, b), c in self.pairs.items():
            pair_strength[a] += int(c)
            pair_strength[b] += int(c)

        def central_score(d: int) -> float:
            return 0.65 * float(self.freq.get(d, 0)) + 0.35 * float(pair_strength.get(d, 0) / 10.0)

        ranked = sorted(UNIVERSO, key=central_score, reverse=True)

        # núcleo pequeno (não exagerar para não colapsar)
        self._cached_nucleo = ranked[:10]

        # satélites: força com núcleo + elite_freq leve
        nucleo_set = set(self._cached_nucleo)

        def sat_score(d: int) -> float:
            s = 0.0
            for nn in nucleo_set:
                s += float(self.pairs.get(_pair_key(d, nn), 0))
            s += 0.45 * float(self.elite_freq.get(d, 0))
            s += 0.15 * float(self.freq.get(d, 0))
            return s

        sat_rank = sorted([d for d in UNIVERSO if d not in nucleo_set], key=sat_score, reverse=True)
        self._cached_satelites = sat_rank[:18]

    def _target_even(self, context: Dict[str, Any], size: int) -> int:
        """
        Alvo de paridade baseado no último resultado, mas com clamp.
        """
        size = int(size)
        base = 7 if size == 15 else 9
        last = context.get("ultimo_resultado") or []
        if last:
            ev = count_even(list(last))
            t = int(round(0.65 * base + 0.35 * ev))
        else:
            t = base
        return int(max(3, min(size - 3, t)))

    def _polish_game(self, jogo: List[int], size: int, target_even: int, context: Dict[str, Any]) -> List[int]:
        """
        Ajuste leve (barato):
        - aproxima paridade
        - reduz runs absurdos (troca 1-2 dezenas)
        """
        jogo = sorted(set(int(x) for x in jogo))
        # garante tamanho
        if len(jogo) > size:
            jogo = jogo[:size]
        while len(jogo) < size:
            cand = random.choice(UNIVERSO)
            if cand not in jogo:
                jogo.append(cand)
        jogo = sorted(set(jogo))[:size]

        # tenta 10 micro-ajustes no máximo (barato)
        freq_rec = context.get("freq_recente") or {}
        for _ in range(10):
            ev = count_even(jogo)
            run = max_consecutive_run(jogo)
            ok_even = abs(ev - target_even) <= 1
            ok_run = run <= 7

            if ok_even and ok_run:
                break

            # escolhe uma dezena para trocar (pior por recência + elite)
            def bad_score(d: int) -> float:
                return 0.6 * float(freq_rec.get(d, 0)) + 0.4 * float(self.elite_freq.get(d, 0))

            # remove um dos piores
            worst = sorted(jogo, key=bad_score)[:3]
            out = random.choice(worst) if worst else random.choice(jogo)

            # escolhe candidato melhor
            pool = [d for d in UNIVERSO if d not in jogo]
            if not pool:
                break

            def good_score(d: int) -> float:
                s = 0.55 * float(freq_rec.get(d, 0))
                s += 0.35 * float(self.elite_freq.get(d, 0))
                # conectividade com núcleo
                for nn in (self._cached_nucleo[:6] if self._cached_nucleo else []):
                    s += 0.10 * float(self.pairs.get(_pair_key(d, nn), 0))
                s += 0.08 * random.random()
                return s

            pool_sorted = sorted(pool, key=good_score, reverse=True)
            newd = random.choice(pool_sorted[: min(10, len(pool_sorted))])

            jogo2 = [x for x in jogo if x != out] + [newd]
            jogo2 = sorted(set(jogo2))
            if len(jogo2) == size:
                # aceita se melhora run/paridade (ou pelo menos não piora muito)
                ev2 = count_even(jogo2)
                run2 = max_consecutive_run(jogo2)
                if abs(ev2 - target_even) <= abs(ev - target_even) and run2 <= run:
                    jogo = jogo2

        return sorted(set(jogo))[:size]
