# Heuristic Step Sequences (heur_step_sequences)

Brain heurístico que gera jogos a partir de sequências de passos (delta sequences).

## Como ativar

O cérebro é registrado automaticamente no `trainer_v2.py` e no backtest. Ele aparece com o id:

```
heur_step_sequences
```

## Parâmetros principais

No `trainer_v2.py`:

```
--steps-mutation-rate 0.10
--steps-exploration-rate 0.10
--steps-delta-max 3
--steps-wrap-mode wrap
--steps-max-attempts-per-game 50
```

## Como gera as sequências

1. Escolhe um número inicial (1..25).
2. Seleciona um padrão base de deltas (14 passos para 15 dezenas) e expande para 18/19.
3. Aplica mutação leve nos deltas (probabilidade configurável).
4. Soma os passos com wrap 1..25, evitando duplicatas via escape incremental.
5. Aplica filtros internos e validações do contexto (RAN/core protect, se disponíveis).
6. Ordena o resultado final e devolve o jogo.

## Aprendizado

O cérebro mantém um estado persistente (cerebro_estado) com estatísticas por padrão:

- `uses`: quantas vezes o padrão foi usado na geração.
- `top_hits`: quantas vezes gerou jogos com 14+ acertos.
- `best_hits`: quantas vezes gerou jogos com 13+ acertos.
- `avg_score`: média dos pontos para jogos do padrão.

Na geração, o peso do padrão aumenta conforme `top_hits`, `best_hits` e `avg_score`,
mantendo exploração controlada para padrões novos.
