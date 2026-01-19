# src/training/trainer_v2.py

from collections import Counter
from tqdm import tqdm

from data.BD.connection import get_conn
from training.core.brain import Brain
from training.utils.comparador import contar_acertos


# ===============================
# ⚙️ CONFIGURAÇÕES DO TREINAMENTO
# ===============================

CONFIG = {
    "jogos_por_concurso": {
        15: 6,
        18: 4,
        20: 2
    },
    "pontos_min_memoria": 11,
    "foco_1415": True
}


# ===============================
# 📥 CARREGA CONCURSOS DO BANCO
# ===============================

def carregar_concursos():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT concurso, d1,d2,d3,d4,d5,d6,d7,d8,d9,
               d10,d11,d12,d13,d14,d15
        FROM concursos
        ORDER BY concurso ASC
    """)

    dados = cursor.fetchall()
    conn.close()

    concursos = []
    for row in dados:
        concursos.append({
            "concurso": row[0],
            "dezenas": list(row[1:])
        })

    return concursos


# ===============================
# 🧠 TREINAMENTO N → N+1
# ===============================

def treinar():
    print("🧠 Iniciando TREINAMENTO V2 (N → N+1)")

    concursos = carregar_concursos()

    if len(concursos) < 2:
        print("❌ Concursos insuficientes para treino")
        return

    brain = Brain(db=None)  # DB será plugado depois
    estatisticas = Counter()

    # ===============================
    # 🔁 LOOP PRINCIPAL
    # ===============================

    for i in tqdm(range(len(concursos) - 1), desc="Treinando"):
        atual = concursos[i]
        proximo = concursos[i + 1]

        concurso_atual = atual["concurso"]
        resultado_real = proximo["dezenas"]

        for tamanho, quantidade in CONFIG["jogos_por_concurso"].items():
            for _ in range(quantidade):
                jogo = brain.gerar_jogo(tamanho)
                pontos = contar_acertos(jogo, resultado_real)

                estatisticas[pontos] += 1

                brain.aprender(
                    concurso=concurso_atual,
                    jogo=jogo,
                    pontos=pontos,
                    resultado_real=resultado_real
                )

                if CONFIG["foco_1415"] and pontos >= 14:
                    print(
                        f"🔥 FOCO 14/15 | Concurso {concurso_atual} "
                        f"| Pontos: {pontos} | Jogo: {jogo}"
                    )

        print(
            f"📘 Concurso {concurso_atual} "
            f"→ previsão {concurso_atual + 1}"
        )

    # ===============================
    # 🔥 CONSOLIDA APRENDIZADO
    # ===============================

    brain.consolidar()

    # ===============================
    # 🎯 GERA JOGOS FINAIS
    # ===============================

    jogos_15, jogos_18 = brain.gerar_jogos_finais(
        qtd_15=10,
        qtd_18=7
    )

    print("\n🎯 JOGOS FINAIS (15 DEZENAS)")
    for j in jogos_15:
        print(j)

    print("\n🎯 JOGOS FINAIS (18 DEZENAS)")
    for j in jogos_18:
        print(j)

    # ===============================
    # 📊 ESTATÍSTICAS
    # ===============================

    print("\n📊 RESUMO DO TREINAMENTO")
    for pontos in sorted(estatisticas.keys(), reverse=True):
        print(f"{pontos} pontos: {estatisticas[pontos]} jogos")

    print("\n✅ TREINAMENTO V2 FINALIZADO COM SUCESSO")


# ===============================
# ▶️ EXECUÇÃO DIRETA
# ===============================

if __name__ == "__main__":
    treinar()
