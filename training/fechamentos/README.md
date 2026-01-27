# Fechamentos (Lotofácil)

Este módulo reúne **fechamentos** para Lotofácil. Um fechamento é um conjunto de regras que, a partir de dezenas selecionadas automaticamente pela IA, gera jogos menores com uma cobertura estatística específica. **Não há garantia de prêmio** — trata-se de um produto informativo/estratégico baseado em critérios estatísticos.

## FC1 (Fechamento Básico)

O **FC1** trabalha com **17 dezenas** (1..25) e gera **4 jogos de 15 dezenas**. A descrição do produto indica que o modelo foi desenhado para **cobrir 13 pontos** quando **15 das 17** dezenas forem acertadas — isso é uma **estratégia estatística**, não uma promessa de resultado.

Principais características:
- Seleção automática das dezenas com **BrainHub** (rankeando dezenas).
- Geração dos jogos com seleção por score + diversidade (cobertura).
- Pontuação final dos jogos com **BrainHub** e tags básicas (paridade, soma, primos, repetidas).

## Como adicionar novos fechamentos

1. Adicione um novo `FechamentoSpec` em `training/fechamentos/specs.py`.
2. Verifique se o gerador automático atende ao novo spec (pool, fixas, jogos).
3. Use o `registry.py` para listar o novo fechamento automaticamente.

> **Aviso**: Este módulo é informativo/estatístico e não oferece garantia de prêmio.
