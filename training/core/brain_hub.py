# training/core/brain_hub.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime
import json
import time

from training.core.brain_interface import BrainInterface


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _as_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _from_json(s: str) -> Any:
    return json.loads(s)


def _to_tuple(jogo: List[int]) -> Tuple[int, ...]:
    return tuple(sorted(int(x) for x in jogo))


def _jaccard(a: Tuple[int, ...], b: Tuple[int, ...]) -> float:
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    uni = len(sa | sb)
    return inter / uni if uni else 0.0


@dataclass
class BrainRow:
    db_id: int
    brain_id: str
    name: str
    category: str
    version: str
    enabled: int


class BrainHub:
    """
    🧠 BrainHub V3 (produção)
    - Orquestra múltiplos cérebros
    - Gera candidatos com diversidade
    - Aprende N -> N+1
    - Persiste tudo no banco
    """

    def __init__(self, db, universo: Optional[List[int]] = None):
        self.db = db
        self.universo = universo or list(range(1, 26))

        self.brains: List[BrainInterface] = []
        self.brain_rows: Dict[str, BrainRow] = {}

        # performance em memória (também vai pro DB)
        self.performance = defaultdict(lambda: {
            "usos": 0,
            "pontos_total": 0,
            "qtd_14": 0,
            "qtd_15": 0,
            "jogos_gerados": 0,
        })

        self._ensure_tables_minimas()

    # ==================================================
    # DB bootstrap (mínimo necessário)
    # ==================================================
    def _ensure_tables_minimas(self) -> None:
        cur = self.db.cursor()

        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS cerebros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brain_id TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                categoria TEXT NOT NULL,
                versao TEXT NOT NULL,
                habilitado INTEGER DEFAULT 1,
                criado_em TEXT,
                atualizado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS cerebro_estado (
                cerebro_id INTEGER PRIMARY KEY,
                estado_json TEXT NOT NULL,
                atualizado_em TEXT
            );

            CREATE TABLE IF NOT EXISTS cerebro_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cerebro_id INTEGER NOT NULL,
                concurso INTEGER NOT NULL,
                media_pontos REAL,
                qtd_14 INTEGER,
                qtd_15 INTEGER,
                jogos_gerados INTEGER,
                atualizado_em TEXT,
                UNIQUE(cerebro_id, concurso)
            );

            CREATE TABLE IF NOT EXISTS logs_execucao (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                modulo TEXT,
                duracao REAL,
                timestamp TEXT
            );
            """
        )

        self.db.commit()

    # ==================================================
    # Registro / carga de cérebros
    # ==================================================
    def register(self, brain: BrainInterface) -> None:
        if not isinstance(brain, BrainInterface):
            raise TypeError("Cérebro inválido: não implementa BrainInterface")

        self.brains.append(brain)
        self._upsert_brain_row(brain)
        self._load_brain_state(brain)
        self._load_brain_perfstate(brain.id)

    def _upsert_brain_row(self, brain: BrainInterface) -> None:
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO cerebros (brain_id, nome, categoria, versao, habilitado, criado_em, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(brain_id) DO UPDATE SET
                nome=excluded.nome,
                categoria=excluded.categoria,
                versao=excluded.versao,
                atualizado_em=excluded.atualizado_em
            """,
            (brain.id, brain.name, brain.category, brain.version, 1, _now(), _now()),
        )
        self.db.commit()

        cur.execute("SELECT id, brain_id, nome, categoria, versao, habilitado FROM cerebros WHERE brain_id = ?", (brain.id,))
        r = cur.fetchone()
        self.brain_rows[brain.id] = BrainRow(
            db_id=int(r[0]),
            brain_id=str(r[1]),
            name=str(r[2]),
            category=str(r[3]),
            version=str(r[4]),
            enabled=int(r[5]),
        )

    def _load_brain_state(self, brain: BrainInterface) -> None:
        row = self.brain_rows.get(brain.id)
        if not row:
            return

        cur = self.db.cursor()
        cur.execute("SELECT estado_json FROM cerebro_estado WHERE cerebro_id = ?", (row.db_id,))
        r = cur.fetchone()
        if not r:
            return

        try:
            state = _from_json(r[0])
        except Exception:
            return

        brain.load_state(state)

    def save_all_states(self) -> None:
        for brain in self.brains:
            if brain.enabled:
                self._save_state(brain)

    def _save_state(self, brain: BrainInterface) -> None:
        row = self.brain_rows.get(brain.id)
        if not row:
            return

        state = brain.save_state()
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO cerebro_estado (cerebro_id, estado_json, atualizado_em)
            VALUES (?,?,?)
            ON CONFLICT(cerebro_id) DO UPDATE SET
                estado_json=excluded.estado_json,
                atualizado_em=excluded.atualizado_em
            """,
            (row.db_id, _as_json(state), _now()),
        )
        self.db.commit()

    def _load_brain_perfstate(self, brain_id: str) -> None:
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
            LIMIT 30
            """,
            (row.db_id,),
        )
        # (opcional) aqui você pode usar isso futuramente para meta-aprendizado

    # ==================================================
    # Context builder (DB -> context)
    # ==================================================
    def build_context(self, concurso_n: int, janela_recente: int = 300) -> Dict[str, Any]:
        """
        Monta contexto leve e eficiente:
        - ultimo_resultado (concurso_n)
        - historico_recente (até janela_recente concursos)
        """
        cur = self.db.cursor()

        # resultado do concurso N
        cur.execute("SELECT dezenas FROM concursos WHERE concurso = ?", (concurso_n,))
        r = cur.fetchone()
        ultimo = self._parse_dezenas(r[0]) if r else []

        # histórico recente até N (para não-clone e tendência)
        cur.execute(
            """
            SELECT dezenas FROM concursos
            WHERE concurso <= ?
            ORDER BY concurso DESC
            LIMIT ?
            """,
            (concurso_n, janela_recente),
        )
        historico = [self._parse_dezenas(x[0]) for x in cur.fetchall()]

        # quentes/frias simples baseado na janela (rápido)
        freq = defaultdict(int)
        for dezenas in historico:
            for d in dezenas:
                freq[d] += 1
        ordenadas = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        quentes = [d for d, _ in ordenadas[:8]]
        frias = [d for d, _ in ordenadas[-8:]] if ordenadas else []

        return {
            "concurso_n": concurso_n,
            "ultimo_resultado": ultimo,
            "historico_recente": historico,
            "dezenas_quentes": quentes,
            "dezenas_frias": frias,
        }

    def _parse_dezenas(self, dezenas_txt: str) -> List[int]:
        # aceita "1,2,3" ou "01,02,03"
        parts = [p.strip() for p in str(dezenas_txt).split(",") if p.strip()]
        return [int(p) for p in parts]

    # ==================================================
    # Geração coletiva com diversidade real
    # ==================================================
    def generate_games(
        self,
        context: Dict[str, Any],
        tamanho: int,
        top_n: int = 50,
        candidatos_por_cerebro: int = 80,
        diversidade_jaccard_max: float = 0.72,
    ) -> List[Dict[str, Any]]:
        """
        Retorna lista de dicts:
        { 'jogo': [...], 'score': float, 'brain_id': str }
        """
        t0 = time.time()

        candidatos: List[Tuple[Tuple[int, ...], float, str]] = []

        for brain in self.brains:
            if not brain.enabled:
                continue

            relev = float(brain.evaluate_context(context))
            if relev <= 0:
                continue

            ctx = dict(context)
            ctx["tamanho"] = tamanho
            ctx["n"] = candidatos_por_cerebro

            jogos = brain.generate(ctx)

            self.performance[brain.id]["usos"] += 1
            self.performance[brain.id]["jogos_gerados"] += len(jogos)

            for jogo in jogos:
                jt = _to_tuple(jogo)
                s_local = float(brain.score_game(list(jt), ctx))
                score_final = (s_local * 0.75) + (relev * 0.25)
                candidatos.append((jt, score_final, brain.id))

        # Ordena por score
        candidatos.sort(key=lambda x: x[1], reverse=True)

        # 1) remove duplicados exatos
        unique: List[Tuple[Tuple[int, ...], float, str]] = []
        seen = set()
        for jt, sc, bid in candidatos:
            if jt in seen:
                continue
            seen.add(jt)
            unique.append((jt, sc, bid))

        # 2) diversidade por Jaccard (evita 50 jogos quase iguais)
        selecionados: List[Tuple[Tuple[int, ...], float, str]] = []
        for jt, sc, bid in unique:
            ok = True
            for sel, _, _ in selecionados:
                if _jaccard(jt, sel) >= diversidade_jaccard_max:
                    ok = False
                    break
            if ok:
                selecionados.append((jt, sc, bid))
            if len(selecionados) >= top_n:
                break

        out = [{"jogo": list(jt), "score": sc, "brain_id": bid} for jt, sc, bid in selecionados]

        self._log_perf("BrainHub.generate_games", time.time() - t0)
        return out

    # ==================================================
    # Aprendizado N -> N+1 (por jogo avaliado)
    # ==================================================
    def learn_one(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
        brain_id: str,
    ) -> None:
        perf = self.performance[brain_id]
        perf["pontos_total"] += pontos
        if pontos >= 14:
            perf["qtd_14"] += 1
        if pontos == 15:
            perf["qtd_15"] += 1

        # chama o cérebro dono
        for b in self.brains:
            if b.id == brain_id:
                b.learn(concurso_n, jogo, resultado_n1, pontos, context)
                break

    # ==================================================
    # Logs / performance
    # ==================================================
    def _log_perf(self, modulo: str, duracao: float) -> None:
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO logs_execucao (modulo, duracao, timestamp) VALUES (?,?,?)",
            (modulo, float(duracao), _now()),
        )
        self.db.commit()
