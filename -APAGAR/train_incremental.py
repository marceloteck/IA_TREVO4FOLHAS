# START/train_incremental.py
from __future__ import annotations

import sys
import traceback
from typing import List, Dict, Any, Tuple

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub, HubConfig

# cérebros do cluster estatístico
from training.core.freq_global_brain import StatFreqGlobalBrain
from training.core.freq_recente_brain import StatFreqRecenteBrain
from training.core.pares_brain import StatParesBrain
from training.core.atraso_brain import StatAtrasoBrain


RECENTE_N = 80  # janela de contexto (leve e efetiva)


def _fetch_concursos(conn) -> List[Tuple[int, List[int]]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT concurso, d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        FROM concursos
        ORDER BY concurso ASC
        """
    )
    rows = cur.fetchall()
    concursos = []
    for r in rows:
        concursos.append((int(r[0]), [int(x) for x in r[1:]]))
    return concursos


def _get_checkpoint(conn) -> int:
    cur = conn.cursor()
    cur.execute("SELECT ultimo_concurso_processado FROM checkpoint WHERE id = 1")
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _build_context(concursos: List[Tuple[int, List[int]]], idx_atual: int) -> Dict[str, Any]:
    """
    Contexto que os cérebros podem usar (leve, mas rico):
    - ultimo_resultado (concurso atual)
    - historico_recente (últimos N concursos até o atual)
    """
    _, atual = concursos[idx_atual]
    ini = max(0, idx_atual - RECENTE_N + 1)
    recentes = [c[1] for c in concursos[ini: idx_atual + 1]]
    return {
        "ultimo_resultado": atual,
        "historico_recente": recentes,
        "recente_n": len(recentes),
    }


def _register_default_brains(hub: BrainHub):
    # cluster estatístico (PASSO 3)
    hub.register(StatFreqGlobalBrain(db=hub.db))
    hub.register(StatFreqRecenteBrain(db=hub.db))
    hub.register(StatParesBrain(db=hub.db))
    hub.register(StatAtrasoBrain(db=hub.db))


def main():
    print("🧠 START | Treino incremental (BrainHub)")

    try:
        conn = get_conn()
        concursos = _fetch_concursos(conn)

        if len(concursos) < 2:
            print("❌ Concursos insuficientes (precisa de pelo menos 2).")
            return 1

        ultimo_proc = _get_checkpoint(conn)

        # acha o índice inicial pelo concurso
        start_idx = 0
        if ultimo_proc > 0:
            for i, (n, _) in enumerate(concursos):
                if n == ultimo_proc:
                    start_idx = i
                    break

        # queremos treinar N -> N+1, então vamos até len-2 no máximo
        if start_idx >= len(concursos) - 1:
            print("✅ Nada para treinar (checkpoint já está no final).")
            return 0

        cfg = HubConfig()
        hub = BrainHub(db=conn, cfg=cfg)
        _register_default_brains(hub)
        hub.load_all_states()

        print(f"📌 Checkpoint atual: {ultimo_proc} | começando no índice {start_idx}")

        # loop N -> N+1
        for i in range(start_idx, len(concursos) - 1):
            concurso_atual, dezenas_atual = concursos[i]
            _, dezenas_proximo = concursos[i + 1]

            context = _build_context(concursos, i)

            print(f"\n🔁 Treinando concurso {concurso_atual} -> {concurso_atual + 1}")
            hub.treinar_concurso(
                concurso_atual=concurso_atual,
                resultado_real_proximo=dezenas_proximo,
                context=context,
            )

        hub.save_all_states()
        print("\n✅ Treino incremental finalizado com sucesso.")
        return 0

    except Exception as e:
        print("\n❌ ERRO no treino incremental:", str(e))
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
