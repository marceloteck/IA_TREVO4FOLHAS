import pandas as pd
from src.database.connection import get_conn

def importar_csv(caminho_csv):
    df = pd.read_csv(caminho_csv, sep=';')

    conn = get_conn()
    cursor = conn.cursor()

    # Limpa dados antigos
    cursor.execute("DELETE FROM concursos")
    cursor.execute("DELETE FROM frequencias")

    # Insere concursos
    for _, row in df.iterrows():
        dezenas = row.iloc[1:16].tolist()
        cursor.execute("""
        INSERT INTO concursos (
            concurso,d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [row.iloc[0]] + dezenas)

    # Calcula frequências
    contagem = {i: 0 for i in range(1, 26)}
    for _, row in df.iterrows():
        for dez in row.iloc[1:16]:
            contagem[int(dez)] += 1

    total = sum(contagem.values())

    for numero, qtd in contagem.items():
        peso = qtd / total
        cursor.execute("""
        INSERT INTO frequencias (numero, quantidade, peso)
        VALUES (?,?,?)
        """, (numero, qtd, peso))

    conn.commit()
    conn.close()
    print("✅ CSV importado e frequências calculadas")

if __name__ == "__main__":
    importar_csv("data\planilhas\Lotofácil.csv")

