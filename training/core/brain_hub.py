# training/core/brain_hub.py

from __future__ import annotations

import json
import math
import random
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime

from training.core.brain_interface import BrainInterface


# =========================================================
# Utils leves
# =========================================================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _as_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)

def _from_json(s: str) -> Any:
    return json.loads(s)

def _jogo_key(jogo: List[int]) -> Tuple[int, ...]:
    return tuple(sorted(jogo))

def _acertos(jogo: List[int], resultado: List[int]) -> int:
    return len(set(jogo) & set(resultado))

def _seq_max(jogo: List[int]) -> int:
    s = set(jogo)
    max_seq = 1
    atual = 1
    for n in sorted(s):
        if (n - 1) in s:
            atual += 1
            max_seq = max(max_seq, atual)
        else:
            atual = 1
    return max_seq

def _pares(jogo: List[int]) -> int:
    return sum(1 for n in jogo if n % 2 == 0)

def _faixas(jogo: List[int]) -> Tuple[int, int, int, int, int]:
    # 1-5, 6-10, 11-15, 16-20, 21-25
    a = sum(1 for d in jogo if 1 <= d <= 5)
    b = sum(1 for d in jogo if 6 <= d <= 10)
    c = sum(1 for d in jogo if 11 <= d <= 15)
    e = sum(1 for d in jogo if 16 <= d <= 20)
    f = sum(1 for d in jogo if 21 <= d <= 25)
    return (a, b, c, e, f)


# =========================================================
# Config do Hub
# =========================================================

@dataclass
class HubConfig:
    # geração
    candidatos_por_cerebro_15: int = 20
    candidatos_por_cerebro_18: int = 12
    top_candidatos_pool: int = 200  # pool global para ensemble

    # seleção natural / pesos
    alpha_ema: float = 0.15  # EMA de performance recente
    min_weight: float = 0.10
    max_weight: float = 3.50
    explore_eps: float = 0.08  # chance de dar boost em cérebro ruim (anti-estagnação)

    # ensemble (restrições leves)
    max_seq_15: int = 4
    max_seq_18: int = 5
    par_ideal_15: Tuple[int, int] = (7, 8)   # pares aceitáveis
    par_ideal_18: Tuple[int, int] = (8, 10)

    # diversidade
    diversidade_min_inter_15: int = 10  # não deixar jogos finais muito iguais entre si
    diversidade_min_inter_18: int = 13


# =========================================================
# Estruturas internas
# =========================================================

@dataclass
class BrainRow:
    db_id: int
    nome: str
    tipo: str
    classe: str
    versao: str
    ativo: int


@dataclass
class PerfState:
    # histórico/estado do HUB sobre cada cérebro (meta-aprendizado)
    ema_media: float = 0.0
    ema_1415: float = 0.0
    usos: int = 0
    last_concurso: int = 0

    def weight(self, cfg: HubConfig) -> float:
        # peso composto: EMA média + EMA de 14/15
        # escala suave e limitada
        base = (self.ema_media * 0.30) + (self.ema_1415 * 1.40)
        # transforma para algo positivo estável
        w = 1.0 + base
        return max(cfg.min_weight, min(cfg.max_weight, w))


# =========================================================
# BrainHub (Evoluído)
# =========================================================

class BrainHub:
    """
    🧠 BrainHub — Meta-Aprendizado real + Persistência BD + Seleção natural + Ensemble.

    Requisitos:
    - self.db deve ser sqlite3.Connection (ou objeto compatível com .cursor(), .commit()).
    - schema deve conter as tabelas:
        cerebros, cerebro_estado, cerebro_jogos, cerebro_performance, checkpoint, logs_execucao
    """

    def __init__(self, db: sqlite3.Connection, config: Optional[HubConfig] = None):
        self.db = db
        self.cfg = config or HubConfig()

        self.brains: List[BrainInterface] = []
        self.brain_rows: Dict[str, BrainRow] = {}          # brain.id -> row
        self.perf: Dict[str, PerfState] = defaultdict(PerfState)  # brain.id -> perfstate

        self._ensure_foreign_keys()

    # -----------------------------------------------------
    # Banco
    # -----------------------------------------------------

    def _ensure_foreign_keys(self) -> None:
        try:
            cur = self.db.cursor()
            cur.execute("PRAGMA foreign_keys = ON;")
            self.db.commit()
        except Exception:
            # SQLite pode ignorar dependendo do driver, mas sem quebrar execução.
            pass

    def _log(self, modulo: str, mensagem: str, duracao: Optional[float] = None) -> None:
        try:
            cur = self.db.cursor()
            cur.execute(
                "INSERT INTO logs_execucao (modulo, mensagem, duracao, criado_em) VALUES (?,?,?,?)",
                (modulo, mensagem, duracao, _now()),
            )
            self.db.commit()
        except Exception:
            # log não deve derrubar o sistema
            pass

    # -----------------------------------------------------
    # Registro de cérebros (e vínculo com BD)
    # -----------------------------------------------------

    def register(self, brain: BrainInterface, *, tipo: str, versao: str, nome: Optional[str] = None) -> None:
        """
        Registra cérebro no Hub e garante que existe uma linha em `cerebros`.
        - tipo: statistical | pattern | hybrid | neural
        - versao: ex "1.0.0"
        """
        if not isinstance(brain, BrainInterface):
            raise TypeError("Cérebro inválido: não implementa BrainInterface")

        brain_name = nome or getattr(brain, "name", brain.id)
        brain_class = brain.__class__.__name__

        row = self._get_or_create_brain_row(
            brain_name=brain_name,
            brain_tipo=tipo,
            brain_class=brain_class,
            brain_versao=versao,
        )

        self.brains.append(brain)
        self.brain_rows[brain.id] = row

        # Carregar estado persistido do cérebro (se houver)
        self._load_brain_state(brain)

        # Carregar meta-performance do cérebro (se houver)
        self._load_brain_perfstate(brain.id)

    def _get_or_create_brain_row(self, brain_name: str, brain_tipo: str, brain_class: str, brain_versao: str) -> BrainRow:
        cur = self.db.cursor()

        # tenta achar por (classe + versao + nome)
        cur.execute(
            """
            SELECT id, nome, tipo, classe, versao, ativo
            FROM cerebros
            WHERE nome = ? AND classe = ? AND versao = ?
            LIMIT 1
            """,
            (brain_name, brain_class, brain_versao),
        )
        r = cur.fetchone()
        if r:
            return BrainRow(db_id=r[0], nome=r[1], tipo=r[2], classe=r[3], versao=r[4], ativo=r[5])

        cur.execute(
            """
            INSERT INTO cerebros (nome, tipo, classe, versao, ativo, criado_em)
            VALUES (?,?,?,?,1,?)
            """,
            (brain_name, brain_tipo, brain_class, brain_versao, _now()),
        )
        self.db.commit()

        brain_db_id = cur.lastrowid
        return BrainRow(db_id=brain_db_id, nome=brain_name, tipo=brain_tipo, classe=brain_class, versao=brain_versao, ativo=1)

    # -----------------------------------------------------
    # Estado de cérebro (persistência)
    # -----------------------------------------------------

    def _load_brain_state(self, brain: BrainInterface) -> None:
        row = self.brain_rows.get(brain.id)
        if not row:
            return

        cur = self.db.cursor()
        cur.execute(
            "SELECT estado_json FROM cerebro_estado WHERE cerebro_id = ?",
            (row.db_id,),
        )
        r = cur.fetchone()
        if not r:
            # sem estado ainda (primeira execução)
            return

        try:
            estado = _from_json(r[0])
        except Exception:
            self._log("BrainHub", f"Falha ao ler JSON do estado do cérebro {brain.id}")
            return

        # Importante: load_state do cérebro pode assumir controle total
        # Para compatibilidade, permitimos ambos:
        # - load_state() sem args (cérebro busca no banco)
        # - load_state(state) com args (cérebro aplica o dict)
        try:
            # tenta com argumento (recomendado)
            brain.load_state(estado)  # type: ignore[arg-type]
        except TypeError:
            # fallback: cérebro usa self.db internamente
            try:
                brain.load_state()
            except Exception:
                pass

    def save_all_states(self) -> None:
        for brain in self.brains:
            self._save_brain_state(brain)

    def _save_brain_state(self, brain: BrainInterface) -> None:
        row = self.brain_rows.get(brain.id)
        if not row:
            return

        # obtém estado do cérebro
        try:
            estado = brain.save_state()
        except Exception as e:
            self._log("BrainHub", f"Erro em save_state() do cérebro {brain.id}: {e}")
            return

        try:
            estado_json = _as_json(estado)
        except Exception as e:
            self._log("BrainHub", f"Erro serializando estado do cérebro {brain.id}: {e}")
            return

        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO cerebro_estado (cerebro_id, estado_json, atualizado_em)
            VALUES (?,?,?)
            ON CONFLICT(cerebro_id) DO UPDATE SET
                estado_json=excluded.estado_json,
                atualizado_em=excluded.atualizado_em
            """,
            (row.db_id, estado_json, _now()),
        )
        self.db.commit()

    # -----------------------------------------------------
    # Meta-performance do Hub (persistência leve)
    # -----------------------------------------------------

    def _load_brain_perfstate(self, brain_id: str) -> None:
        """
        Carrega uma visão resumida da performance recente do cérebro
        usando cerebro_performance (últimos concursos).
        """
        row = self.brain_rows.get(brain_id)
        if not row:
            return

        cur = self.db.cursor()
        cur.execute(
            """
            SELECT concurso, media_pontos, qtd_14, qtd_15, jogos_gerados
            FROM cerebro_performance
            WHERE cerebro_id = ?
            ORDER BY concurso DESC
            LIMIT 20
            """,
            (row.db_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return

        # constrói EMAs a partir do histórico
        ps = self.perf[brain_id]
        # reconstroi do mais antigo pro mais novo
        for concurso, media, q14, q15, jogos_gerados in reversed(rows):
            if jogos_gerados and jogos_gerados > 0:
                taxa_1415 = (float(q14 or 0) + float(q15 or 0)) / float(jogos_gerados)
            else:
                taxa_1415 = 0.0

            ps.ema_media = (1 - self.cfg.alpha_ema) * ps.ema_media + self.cfg.alpha_ema * float(media or 0.0)
            ps.ema_1415 = (1 - self.cfg.alpha_ema) * ps.ema_1415 + self.cfg.alpha_ema * float(taxa_1415)
            ps.last_concurso = int(concurso or 0)

    def _update_perfstate_after_concurso(self, brain_id: str, concurso: int, media_pontos: float, qtd_14: int, qtd_15: int, jogos_gerados: int) -> None:
        ps = self.perf[brain_id]
        ps.usos += 1
        ps.last_concurso = concurso

        taxa_1415 = ((qtd_14 + qtd_15) / jogos_gerados) if jogos_gerados > 0 else 0.0

        ps.ema_media = (1 - self.cfg.alpha_ema) * ps.ema_media + self.cfg.alpha_ema * media_pontos
        ps.ema_1415 = (1 - self.cfg.alpha_ema) * ps.ema_1415 + self.cfg.alpha_ema * taxa_1415

    # -----------------------------------------------------
    # Seleção natural (peso do cérebro para ensemble)
    # -----------------------------------------------------

    def _brain_weight(self, brain_id: str) -> float:
        w = self.perf[brain_id].weight(self.cfg)
        # exploração: às vezes dá chance extra para não “congelar” o sistema
        if random.random() < self.cfg.explore_eps:
            w *= 1.15
        return w

    # -----------------------------------------------------
    # Geração de candidatos (pool global)
    # -----------------------------------------------------

    def _generate_pool_for_size(self, context: Dict[str, Any], tamanho: int) -> List[Tuple[List[int], float, str]]:
        """
        Retorna lista de (jogo, score_global, brain_id)
        """
        candidatos: List[Tuple[List[int], float, str]] = []

        for brain in self.brains:
            if not getattr(brain, "enabled", True):
                continue

            # relevância contextual do cérebro
            try:
                rel = float(brain.evaluate_context(context))
            except Exception:
                rel = 1.0

            if rel <= 0:
                continue

            # quantos candidatos pedir deste cérebro
            if tamanho == 15:
                n = self.cfg.candidatos_por_cerebro_15
            else:
                n = self.cfg.candidatos_por_cerebro_18

            # chama o cérebro
            try:
                jogos = brain.generate({**context, "tamanho": tamanho, "n": n})
            except Exception as e:
                self._log("BrainHub", f"Erro generate() cérebro {brain.id}: {e}")
                continue

            # normaliza retorno (permite cérebro retornar 1 jogo só)
            if jogos and isinstance(jogos[0], int):  # type: ignore[index]
                jogos = [jogos]  # type: ignore[assignment]

            w_brain = self._brain_weight(brain.id)

            for jogo in (jogos or [])[:n]:
                try:
                    s_local = float(brain.score_game(jogo))
                except Exception:
                    s_local = 0.0

                # score global: peso cérebro + relevância contexto
                score_global = (s_local * 0.75 + rel * 0.25) * w_brain
                candidatos.append((sorted(jogo), score_global, brain.id))

        # ordena e remove duplicados mantendo o melhor score
        candidatos.sort(key=lambda x: x[1], reverse=True)

        best_by_key: Dict[Tuple[int, ...], Tuple[List[int], float, str]] = {}
        for jogo, score, bid in candidatos:
            k = _jogo_key(jogo)
            if k not in best_by_key:
                best_by_key[k] = (jogo, score, bid)

        pool = list(best_by_key.values())
        pool.sort(key=lambda x: x[1], reverse=True)
        return pool[: self.cfg.top_candidatos_pool]

    # -----------------------------------------------------
    # Ensemble (votação por dezena + diversidade + regras)
    # -----------------------------------------------------

    def _build_final_games(self, pool: List[Tuple[List[int], float, str]], tamanho: int, qtd: int) -> List[List[int]]:
        """
        Constrói jogos finais a partir do pool via votação por dezena,
        com restrições leves (seq/paridade/diversidade).
        """
        if not pool:
            return []

        # 1) votação por dezena ponderada
        votos = Counter()
        for jogo, score, brain_id in pool:
            # voto do jogo vale seu score (já inclui peso do cérebro)
            for d in jogo:
                votos[d] += score

        # 2) monta uma lista ordenada de dezenas por “força”
        ordenadas = [d for d, _ in votos.most_common(25)]

        # 3) gerador de um jogo por mistura de:
        #    - topo votos
        #    - uma fração de exploração (anti-vício)
        def gerar_um() -> List[int]:
            top_base = ordenadas[: max(18, tamanho)]
            # exploração: mistura alguns números mais abaixo
            explor = ordenadas[18:]
            jogo = set()

            # pega ~80% do top, ~20% exploração (ajustável)
            alvo_top = int(tamanho * 0.80)
            alvo_exp = tamanho - alvo_top

            jogo.update(random.sample(top_base, min(alvo_top, len(top_base))))
            if explor and alvo_exp > 0:
                jogo.update(random.sample(explor, min(alvo_exp, len(explor))))

            # completa se faltou
            universo = list(range(1, 26))
            while len(jogo) < tamanho:
                jogo.add(random.choice(universo))

            return sorted(jogo)

        # 4) filtros leves
        def passa_regras(jogo: List[int]) -> bool:
            if tamanho == 15:
                if _seq_max(jogo) > self.cfg.max_seq_15:
                    return False
                p = _pares(jogo)
                if p < self.cfg.par_ideal_15[0] or p > self.cfg.par_ideal_15[1]:
                    return False
            else:
                if _seq_max(jogo) > self.cfg.max_seq_18:
                    return False
                p = _pares(jogo)
                if p < self.cfg.par_ideal_18[0] or p > self.cfg.par_ideal_18[1]:
                    return False

            # distribuição por faixas (evita concentração extrema)
            fa = _faixas(jogo)
            if max(fa) - min(fa) >= 6:
                return False

            return True

        # 5) diversidade entre jogos finais
        def diverso(jogo: List[int], escolhidos: List[List[int]]) -> bool:
            if not escolhidos:
                return True
            inter_min = self.cfg.diversidade_min_inter_15 if tamanho == 15 else self.cfg.diversidade_min_inter_18
            s = set(jogo)
            for e in escolhidos:
                if len(s & set(e)) >= inter_min:
                    return False
            return True

        finais: List[List[int]] = []
        tentativas = 0
        limite = 5000 if tamanho == 15 else 7000

        while len(finais) < qtd and tentativas < limite:
            tentativas += 1
            j = gerar_um()
            if not passa_regras(j):
                continue
            if not diverso(j, finais):
                continue
            finais.append(j)

        # fallback: se regras estiverem muito duras, completa com top do pool
        if len(finais) < qtd:
            for jogo, _, _ in pool:
                if len(finais) >= qtd:
                    break
                if jogo not in finais and passa_regras(jogo) and diverso(jogo, finais):
                    finais.append(jogo)

        return finais[:qtd]

    # -----------------------------------------------------
    # API pública: gerar para o próximo concurso (sem saber o resultado)
    # -----------------------------------------------------

    def gerar_para_proximo(self, context: Dict[str, Any], qtd_15: int = 10, qtd_18: int = 7) -> Dict[str, Any]:
        """
        Gera jogos finais para o próximo sorteio usando ensemble dos cérebros.
        (Não usa resultado real — é para produção)
        """
        pool_15 = self._generate_pool_for_size(context, 15)
        pool_18 = self._generate_pool_for_size(context, 18)

        jogos_15 = self._build_final_games(pool_15, 15, qtd_15)
        jogos_18 = self._build_final_games(pool_18, 18, qtd_18)

        return {
            "jogos_15": jogos_15,
            "jogos_18": jogos_18,
            "debug": {
                "pool_15": len(pool_15),
                "pool_18": len(pool_18),
                "brains_ativos": [b.id for b in self.brains if getattr(b, "enabled", True)],
            },
        }

    # -----------------------------------------------------
    # Treino incremental N -> N+1 (com persistência e métricas)
    # -----------------------------------------------------

    def treinar_concurso(self, concurso_atual: int, resultado_real_proximo: List[int], context: Dict[str, Any]) -> None:
        """
        Treina todos os cérebros no formato N -> N+1:
        - Cada cérebro gera candidatos (15 e 18)
        - Avalia pontos contra resultado_real_proximo
        - Salva jogos e performance no BD
        - Chama learn() do cérebro
        - Atualiza meta-performance do Hub (EMA)
        - Salva estados
        """
        # 15
        self._treinar_tamanho(concurso_atual, resultado_real_proximo, context, tamanho=15)
        # 18
        self._treinar_tamanho(concurso_atual, resultado_real_proximo, context, tamanho=18)

        # checkpoint global
        self._update_checkpoint(concurso_atual, "treino_incremental")
        # salva estados de todos
        self.save_all_states()

    def _treinar_tamanho(self, concurso_atual: int, resultado_real_proximo: List[int], context: Dict[str, Any], tamanho: int) -> None:
        for brain in self.brains:
            if not getattr(brain, "enabled", True):
                continue

            row = self.brain_rows.get(brain.id)
            if not row:
                continue

            # gera N candidatos por cérebro
            n = self.cfg.candidatos_por_cerebro_15 if tamanho == 15 else self.cfg.candidatos_por_cerebro_18

            try:
                jogos = brain.generate({**context, "tamanho": tamanho, "n": n, "modo": "treino"})
            except Exception as e:
                self._log("BrainHub", f"Erro generate treino cérebro {brain.id}: {e}")
                continue

            if jogos and isinstance(jogos[0], int):  # type: ignore[index]
                jogos = [jogos]  # type: ignore[assignment]

            jogos = (jogos or [])[:n]

            # avalia e registra
            pontos_list: List[int] = []
            dist = Counter()

            max_p = -1
            for jogo in jogos:
                p = _acertos(jogo, resultado_real_proximo)
                pontos_list.append(p)
                dist[p] += 1
                max_p = max(max_p, p)

                # salva jogo no BD (auditoria)
                self._insert_cerebro_jogo(row.db_id, concurso_atual, tamanho, jogo, p)

                # cérebro aprende (N -> N+1)
                try:
                    brain.learn(concurso_atual, jogo, resultado_real_proximo, p)
                except Exception as e:
                    self._log("BrainHub", f"Erro learn() cérebro {brain.id}: {e}")

            # performance consolidada do cérebro neste concurso/tamanho
            jogos_gerados = len(jogos)
            media = float(sum(pontos_list) / jogos_gerados) if jogos_gerados else 0.0

            qtd_11 = dist.get(11, 0) + dist.get(12, 0) + dist.get(13, 0) + dist.get(14, 0) + dist.get(15, 0)
            qtd_12 = dist.get(12, 0) + dist.get(13, 0) + dist.get(14, 0) + dist.get(15, 0)
            qtd_13 = dist.get(13, 0) + dist.get(14, 0) + dist.get(15, 0)
            qtd_14 = dist.get(14, 0)
            qtd_15 = dist.get(15, 0)

            self._insert_cerebro_performance(
                cerebro_id=row.db_id,
                concurso=concurso_atual,
                jogos_gerados=jogos_gerados,
                media_pontos=media,
                max_pontos=max_p if max_p >= 0 else 0,
                qtd_11=qtd_11,
                qtd_12=qtd_12,
                qtd_13=qtd_13,
                qtd_14=qtd_14,
                qtd_15=qtd_15,
            )

            # atualiza meta-performance do hub (EMA)
            self._update_perfstate_after_concurso(brain.id, concurso_atual, media, qtd_14, qtd_15, jogos_gerados)

    def _insert_cerebro_jogo(self, cerebro_db_id: int, concurso: int, tamanho: int, jogo: List[int], pontos: int) -> None:
        try:
            cur = self.db.cursor()
            cur.execute(
                """
                INSERT INTO cerebro_jogos (cerebro_id, concurso, tamanho_jogo, jogo, pontos, criado_em)
                VALUES (?,?,?,?,?,?)
                """,
                (cerebro_db_id, concurso, tamanho, _as_json(sorted(jogo)), pontos, _now()),
            )
            self.db.commit()
        except Exception as e:
            self._log("BrainHub", f"Erro insert cerebro_jogos: {e}")

    def _insert_cerebro_performance(
        self,
        cerebro_id: int,
        concurso: int,
        jogos_gerados: int,
        media_pontos: float,
        max_pontos: int,
        qtd_11: int,
        qtd_12: int,
        qtd_13: int,
        qtd_14: int,
        qtd_15: int,
    ) -> None:
        try:
            cur = self.db.cursor()
            cur.execute(
                """
                INSERT INTO cerebro_performance
                (cerebro_id, concurso, jogos_gerados, media_pontos, max_pontos,
                 qtd_11, qtd_12, qtd_13, qtd_14, qtd_15, criado_em)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (cerebro_id, concurso, jogos_gerados, media_pontos, max_pontos,
                 qtd_11, qtd_12, qtd_13, qtd_14, qtd_15, _now()),
            )
            self.db.commit()
        except Exception as e:
            self._log("BrainHub", f"Erro insert cerebro_performance: {e}")

    def _update_checkpoint(self, ultimo_concurso: int, ultima_execucao: str) -> None:
        try:
            cur = self.db.cursor()
            cur.execute(
                """
                INSERT INTO checkpoint (id, ultimo_concurso_processado, ultima_execucao, atualizado_em)
                VALUES (1,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    ultimo_concurso_processado=excluded.ultimo_concurso_processado,
                    ultima_execucao=excluded.ultima_execucao,
                    atualizado_em=excluded.atualizado_em
                """,
                (ultimo_concurso, ultima_execucao, _now()),
            )
            self.db.commit()
        except Exception as e:
            self._log("BrainHub", f"Erro checkpoint: {e}")

    # -----------------------------------------------------
    # Relatório do Hub
    # -----------------------------------------------------

    def report(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for brain in self.brains:
            row = self.brain_rows.get(brain.id)
            ps = self.perf.get(brain.id, PerfState())
            out[brain.id] = {
                "db_id": row.db_id if row else None,
                "nome": row.nome if row else getattr(brain, "name", brain.id),
                "tipo": row.tipo if row else None,
                "classe": row.classe if row else brain.__class__.__name__,
                "versao": row.versao if row else None,
                "enabled": getattr(brain, "enabled", True),
                "weight_atual": round(ps.weight(self.cfg), 4),
                "ema_media": round(ps.ema_media, 4),
                "ema_1415": round(ps.ema_1415, 6),
                "usos": ps.usos,
                "last_concurso": ps.last_concurso,
                "brain_report": self._safe_brain_report(brain),
            }
        return out

    def _safe_brain_report(self, brain: BrainInterface) -> Dict[str, Any]:
        try:
            r = brain.report()
            return r if isinstance(r, dict) else {"report": str(r)}
        except Exception as e:
            return {"erro_report": str(e)}
