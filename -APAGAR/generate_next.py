# START/generate_next.py
from __future__ import annotations

import traceback
from typing import List, Tuple, Dict, Any

from data.BD.connection import get_conn
from training.core.brain_hub import BrainHub, HubConfig

from training.core.freq_global_brain import StatFreqGlobalBrain
from training.core.freq_recente_brain import StatFreqRecenteBrain
from training.core.pares_brain import StatParesBrain
from training.core.atraso_brain import StatAtrasoBrain


RECENTE_N = 80


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


def _build_context(concursos: List[Tuple[int, List[int]]]) -> Dict[str, Any]:
    idx = len(concursos) - 1
    _, ultimo = concursos[idx]
    ini = max(0, idx - RECENTE_N + 1)
    recentes = [c[1] for c in concursos[ini: idx + 1]]
    return {
        "ultimo_resultado": ultimo,
        "historico_recente": recentes,
        "recente_n": len(recentes),
        "modo": "producao",
    }


def _register_default_brains(hub: BrainHub):
    hub.register(StatFreqGlobalBrain(db=hub.db))
    hub.register(StatFreqRecenteBrain(db=hub.db))
    hub.register(StatParesBrain(db=hub.db))
    hub.register(StatAtrasoBrain(db=hub.db))


def main():
    print("🎯 START | Gerar jogos para o próximo concurso (BrainHub)")

    try:
        conn = get_conn()
        concursos = _fetch_concursos(conn)
        if not concursos:
            print("❌ Sem concursos no banco.")
            return 1

        context = _build_context(concursos)

        cfg = HubConfig()
        hub = BrainHub(db=conn, cfg=cfg)
        _register_default_brains(hub)
        hub.load_all_states()

        saida = hub.gerar_para_proximo(context=context, qtd_15=10, qtd_18=7)

        jogos_15 = saida["jogos_15"]
        jogos_18 = saida["jogos_18"]

        ultimo_concurso = concursos[-1][0]
        print(f"\n📌 Último concurso no banco: {ultimo_concurso}")
        print("\n🎯 JOGOS 15 DEZENAS")
        for i, j in enumerate(jogos_15, 1):
            print(f"Jogo {i:02d}: {j}")

        print("\n🎯 JOGOS 18 DEZENAS")
        for i, j in enumerate(jogos_18, 1):
            print(f"Jogo {i:02d}: {j}")

        dbg = saida.get("debug", {})
        print("\n🧪 DEBUG:", dbg)

        print("\n✅ Geração concluída.")
        return 0

    except Exception as e:
        print("\n❌ ERRO na geração:", str(e))
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
