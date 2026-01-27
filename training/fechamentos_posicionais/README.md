# Fechamentos Posicionais (Lotofácil)

Este módulo implementa **fechamentos posicionais** para Lotofácil com geração 100% automática. A IA escolhe o pool, as fixas (quando existirem) e a distribuição por grupos, gerando jogos finais conforme o spec do fechamento. **Não há garantia de prêmio** — trata-se de um produto estatístico e informativo.

## Regras gerais
- O usuário não escolhe dezenas.
- O BrainHub é usado para ranquear dezenas, formar grupos e pontuar jogos.
- Cada fechamento define `total_numbers`, `fixed_required_count`, `game_size`, `games_count` e `group_distribution`.

## Aviso legal
- “Garantia” é declarada pelo método combinatório do fechamento (informativo).
- **Produto estatístico e informativo. Loterias envolvem aleatoriedade. Não existe garantia de prêmio.**
