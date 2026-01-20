# training/brains/statistical/elite_memory_brain.py
from __future__ import annotations

import random
from collections import Counter
from typing import Any, Dict, List, Tuple

from training.core.base_brain import BaseBrain
from training.brains._utils import UNIVERSO, weighted_sample_without_replacement, count_even, max_consecutive_run


def _pair(a: int, b: int) -> Tuple[int, int]:
    return (a, b) if a < b else (b, a)


class StatEliteMemoryBrain(BaseBrain):
    """
    Cérebro Estatístico: Elite Memory (14/15) + Memória Forte (11+)
    ----------------------------------------------------------------
    Fonte oficial de aprendizado: tabela memoria_jogos do SQLite.

    O que ele faz:
    - Lê incrementalmente memoria_jogos (somente novos IDs) e aprende padrões reais
    - Dá peso muito maior para acertos >= 14
    - Mantém:
        * elite_freq: frequência das dezenas em jogos 14+
        * strong_freq: frequência das dezenas em jogos 11+
        * elite_pairs: pares fortes dentro dos jogos 14+
    - Gera jogos:
        * começa com núcleo elite (vários picks)
        * completa com dezenas fortes + recência do contexto
        * controla paridade e run de sequência (leve)

    Importante:
    - Não depende de CSV nem de reprocessamento completo.
    - Aprende “para sempre” (24/7) a cada novo jogo salvo em memoria_jogos.
    """

    def __init__(
        self,
        db_conn,
        min_strong: int = 11,
        min_elite: int = 14,
        keep_pairs: int = 1200,
        version: str = "v1",
    ):
        super().__init__(
            db_conn=db_conn,
            brain_id="stat_elite_memory",
            name="Stat - Elite Memory (memoria_jogos 14/15)",
            category="estatistico",
            version=version,
        )

        self.min_strong = int(min_strong)
        self.min_elite = int(min_elite)
        self.keep_pairs = int(max(300, min(10000, keep_pairs)))

        # Estado incremental
        self.last_mem_id: int = 0

        # Memórias internas (leves e fortes)
        self.strong_freq: Counter[int] = Counter()   # jogos >= 11
        self.elite_freq: Counter[int] = Counter()    # jogos >= 14
        self.elite_pairs: Counter[Tuple[int, int]] = Counter()

        self.learn_steps: int = 0

        # Carrega estado do banco e sincroniza com memoria_jogos
        self.load_state()
        self._rebuild_from_state()
        self._sync_from_db(limit_rows=50000)  # 1a carga: tenta pegar bastante, mas só 1 vez

    # ==========================
    # BrainInterface
    # ==========================
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        # Quanto mais elite acumulado, mais relevante (ele vira um “professor”)
        elite_total = sum(self.elite_freq.values())
        if elite_total <= 50:
            return 0.85
        if elite_total <= 200:
            return 0.92
        return 1.00

    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        size = int(size)
        n = int(n)
        if size not in (15, 18):
            size = 15

        # sincroniza sempre um pouquinho (incremental) para manter atualizado
        self._sync_from_db(limit_rows=1200)

        freq_rec = context.get("freq_recente") or {}
        ranked_rec = sorted(UNIVERSO, key=lambda d: freq_rec.get(d, 0), reverse=True)
        top_rec = ranked_rec[:12] if ranked_rec else []

        # Núcleos principais
        elite_rank = [d for d, _ in self.elite_freq.most_common(18)]
        strong_rank = [d for d, _ in self.strong_freq.most_common(22)]
        if not elite_rank:
            elite_rank = strong_rank[:]
        if not strong_rank:
            strong_rank = UNIVERSO[:]

        # alvo paridade (leve)
        target_even = self._target_even(context=context, size=size)

        jogos: List[List[int]] = []
        for _ in range(n):
            jogo = set()

            # 1) núcleo elite
            k_elite = 6 if size == 15 else 7
            elite_pool = [d for d in elite_rank if d not in jogo]
            if elite_pool:
                k_elite = min(k_elite, len(elite_pool))
                # pondera por elite_freq
                w = {d: float(self.elite_freq.get(d, 0) + 1.0) for d in elite_pool}
                picks = weighted_sample_without_replacement(w, k_elite)
                jogo.update(picks)

            # 2) completa usando pares elite + strong + recência
            while len(jogo) < size:
                # escolhe estratégia
                r = random.random()

                # 2a) usa pares elite (conectividade)
                if r < 0.45 and self.elite_pairs and jogo:
                    anchor = random.choice(list(jogo))
                    # pega candidatos bem conectados ao anchor
                    cand = []
                    for d in UNIVERSO:
                        if d in jogo:
                            continue
                        cand.append((d, self.elite_pairs.get(_pair(int(anchor), int(d)), 0)))
                    cand.sort(key=lambda x: x[1], reverse=True)
                    if cand and cand[0][1] > 0:
                        top = [d for d, sc in cand[:10] if sc > 0]
                        if top:
                            jogo.add(random.choice(top))
                            continue

                # 2b) recência (contexto)
                if r < 0.70 and top_rec:
                    jogo.add(random.choice(top_rec))
                    continue

                # 2c) strong
                if r < 0.92 and strong_rank:
                    jogo.add(random.choice(strong_rank[:18]))
                    continue

                # 2d) exploração
                jogo.add(random.choice(UNIVERSO))

            jogo_list = sorted(jogo)
            jogo_list = self._polish(jogo_list, size=size, target_even=target_even, context=context)
            jogos.append(sorted(jogo_list))

        return jogos

    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        if not jogo:
            return 0.0

        # sincroniza leve (para score não ficar defasado em long-run)
        if self.learn_steps % 20 == 0:
            self._sync_from_db(limit_rows=300)

        # score por elite_freq + pares elite + recência
        freq_rec = context.get("freq_recente") or {}

        # 1) elite_freq normalizado
        if self.elite_freq:
            mx = max(self.elite_freq.values())
            s_elite = sum((self.elite_freq.get(int(d), 0) / mx) for d in jogo) / len(jogo)
        else:
            s_elite = 0.15

        # 2) strong_freq normalizado (fallback)
        if self.strong_freq:
            mxs = max(self.strong_freq.values())
            s_strong = sum((self.strong_freq.get(int(d), 0) / mxs) for d in jogo) / len(jogo)
        else:
            s_strong = 0.10

        # 3) pares elite internos
        ps = 0.0
        for i in range(len(jogo)):
            for j in range(i + 1, len(jogo)):
                ps += float(self.elite_pairs.get(_pair(int(jogo[i]), int(jogo[j])), 0))
        ps = min(1.0, ps / 350.0)  # escala comparativa

        # 4) recência leve
        if freq_rec:
            m = max(freq_rec.values()) or 1
            s_rec = sum((freq_rec.get(int(d), 0) / m) for d in jogo) / len(jogo)
        else:
            s_rec = 0.10

        # 5) penaliza run exagerado
        run = max_consecutive_run(jogo)
        pen_run = max(0.0, (run - 6) / 6.0)

        # composição
        score = (0.45 * s_elite) + (0.18 * s_strong) + (0.22 * ps) + (0.15 * s_rec) - (0.10 * pen_run)
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
        Aqui o “learn” serve para:
        - manter contador interno
        - registrar performance
        - e sincronizar incrementalmente a memória vencedora do banco
        """
        self.learn_steps += 1

        # sincroniza incremental (puxa novos jogos salvos pelo trainer)
        self._sync_from_db(limit_rows=900)

        # registra performance leve
        self._perf_update(concurso=int(concurso_n), pontos=int(pontos), jogos_gerados=1)

    # ==========================
    # Persistência
    # ==========================
    def save_state(self) -> None:
        # poda pares para ficar leve
        if len(self.elite_pairs) > self.keep_pairs:
            self.elite_pairs = Counter(dict(self.elite_pairs.most_common(self.keep_pairs)))

        self.state = {
            "min_strong": int(self.min_strong),
            "min_elite": int(self.min_elite),
            "keep_pairs": int(self.keep_pairs),
            "last_mem_id": int(self.last_mem_id),
            "learn_steps": int(self.learn_steps),
            "strong_freq": {str(k): int(v) for k, v in self.strong_freq.items()},
            "elite_freq": {str(k): int(v) for k, v in self.elite_freq.items()},
            "elite_pairs": [[int(a), int(b), int(c)] for (a, b), c in self.elite_pairs.most_common(self.keep_pairs)],
        }
        super().save_state()

    def load_state(self) -> None:
        super().load_state()

    def report(self) -> Dict[str, Any]:
        elite_top = [d for d, _ in self.elite_freq.most_common(12)]
        strong_top = [d for d, _ in self.strong_freq.most_common(12)]
        return {
            **super().report(),
            "learn_steps": int(self.learn_steps),
            "last_mem_id": int(self.last_mem_id),
            "elite_top12": elite_top,
            "strong_top12": strong_top,
            "elite_pairs_kept": int(len(self.elite_pairs)),
        }

    # ==========================
    # Internos
    # ==========================
    def _rebuild_from_state(self) -> None:
        try:
            self.min_strong = int(self.state.get("min_strong", self.min_strong))
            self.min_elite = int(self.state.get("min_elite", self.min_elite))
            self.keep_pairs = int(self.state.get("keep_pairs", self.keep_pairs))
            self.last_mem_id = int(self.state.get("last_mem_id", 0))
            self.learn_steps = int(self.state.get("learn_steps", 0))

            sf = self.state.get("strong_freq") or {}
            self.strong_freq = Counter({int(k): int(v) for k, v in sf.items()})

            ef = self.state.get("elite_freq") or {}
            self.elite_freq = Counter({int(k): int(v) for k, v in ef.items()})

            ep = self.state.get("elite_pairs") or []
            self.elite_pairs = Counter()
            for a, b, c in ep:
                self.elite_pairs[_pair(int(a), int(b))] = int(c)
        except Exception:
            self.last_mem_id = 0
            self.learn_steps = 0
            self.strong_freq = Counter()
            self.elite_freq = Counter()
            self.elite_pairs = Counter()

    def _sync_from_db(self, limit_rows: int = 1200) -> None:
        """
        Lê incrementalmente novos registros em memoria_jogos:
        - respeita last_mem_id (não reprocessa)
        - atualiza strong_freq, elite_freq, elite_pairs
        """
        cur = self.db.cursor()
        cur.execute(
            f"""
            SELECT id, acertos,
                   d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18
            FROM memoria_jogos
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(self.last_mem_id), int(limit_rows)),
        )
        rows = cur.fetchall()
        if not rows:
            return

        for row in rows:
            rid = int(row[0])
            acertos = int(row[1])
            dezenas = [x for x in row[2:] if x is not None]
            dezenas = sorted(set(int(x) for x in dezenas))
            if not dezenas:
                self.last_mem_id = max(self.last_mem_id, rid)
                continue

            # forte
            if acertos >= self.min_strong:
                self.strong_freq.update(dezenas)

            # elite
            if acertos >= self.min_elite:
                self.elite_freq.update(dezenas)
                for i in range(len(dezenas)):
                    for j in range(i + 1, len(dezenas)):
                        self.elite_pairs[_pair(dezenas[i], dezenas[j])] += 1

            self.last_mem_id = max(self.last_mem_id, rid)

        # poda pares de vez em quando
        if len(self.elite_pairs) > self.keep_pairs * 2:
            self.elite_pairs = Counter(dict(self.elite_pairs.most_common(self.keep_pairs)))

    def _target_even(self, context: Dict[str, Any], size: int) -> int:
        size = int(size)
        base = 7 if size == 15 else 9
        last = context.get("ultimo_resultado") or []
        if last:
            ev = count_even(list(last))
            t = int(round(0.60 * base + 0.40 * ev))
        else:
            t = base
        return int(max(3, min(size - 3, t)))

    def _polish(self, jogo: List[int], size: int, target_even: int, context: Dict[str, Any]) -> List[int]:
        """
        Micro-ajuste barato:
        - aproxima paridade
        - evita runs gigantes
        """
        jogo = sorted(set(int(x) for x in jogo))[:size]
        while len(jogo) < size:
            d = random.choice(UNIVERSO)
            if d not in jogo:
                jogo.append(d)
        jogo = sorted(set(jogo))[:size]

        freq_rec = context.get("freq_recente") or {}

        for _ in range(10):
            ev = count_even(jogo)
            run = max_consecutive_run(jogo)
            ok_even = abs(ev - target_even) <= 1
            ok_run = run <= 7
            if ok_even and ok_run:
                break

            # remove um "pior" (baixa elite + baixa recência)
            def bad(d: int) -> float:
                return 0.7 * float(self.elite_freq.get(d, 0)) + 0.3 * float(freq_rec.get(d, 0))

            worst = sorted(jogo, key=bad)[:3]
            out = random.choice(worst) if worst else random.choice(jogo)

            pool = [d for d in UNIVERSO if d not in jogo]
            if not pool:
                break

            def good(d: int) -> float:
                s = 0.75 * float(self.elite_freq.get(d, 0))
                s += 0.35 * float(self.strong_freq.get(d, 0))
                s += 0.25 * float(freq_rec.get(d, 0))
                s += 0.10 * random.random()
                return s

            pool_sorted = sorted(pool, key=good, reverse=True)
            newd = random.choice(pool_sorted[: min(10, len(pool_sorted))])

            cand = sorted(set([x for x in jogo if x != out] + [newd]))
            if len(cand) == size:
                # aceita se melhora (ou não piora) os critérios
                ev2 = count_even(cand)
                run2 = max_consecutive_run(cand)
                if abs(ev2 - target_even) <= abs(ev - target_even) and run2 <= run:
                    jogo = cand

        return sorted(set(jogo))[:size]
