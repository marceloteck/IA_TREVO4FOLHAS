# training/utils/comparador.py

def contar_acertos(jogo, resultado):
    """
    Conta quantos números do jogo estão presentes no resultado real.

    Args:
        jogo (list[int]): dezenas geradas pela IA
        resultado (list[int]): dezenas do concurso real

    Returns:
        int: quantidade de acertos
    """
    if not jogo or not resultado:
        return 0

    return len(set(jogo) & set(resultado))
