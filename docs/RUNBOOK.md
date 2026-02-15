# RUNBOOK — IA_TREVO4FOLHAS 24/7

## Como rodar (modo seguro)
- Execução contínua segura (paper/research):
  - `python -m training.run_continuous --safe-default`
- Execução curta de smoke:
  - `python -m training.backtest.backtest_smart_engine --steps 20 --panel 0 --heartbeat-seconds 5`

## Healthcheck
- Diagnóstico rápido do ambiente/checkpoints:
  - `python -m training.healthcheck`
- O healthcheck valida:
  - range da tabela `concursos`
  - checkpoint principal (`checkpoint.id=1`)
  - checkpoint meta válido
  - checkpoint incremental em `logs/checkpoint_incremental.json`

## Como interpretar travas e watchdog
- Heartbeat deve aparecer em fases longas (`generate_candidates`, `evaluate_hits`, `db_commit`) com `phase`, `detail`, `i/n`, `elapsed`, `rate`.
- Se ficar sem heartbeat além do limite, watchdog emite:
  - aviso com estado atual
  - dump leve de stack (controlado por cooldown)
- Ajuste timeout por env var:
  - `IA_WATCHDOG_SECONDS=60`

## Onde olhar logs
- Console principal do engine (heartbeat + governance + resumo)
- `logs/checkpoint_incremental.json`
- `logs/validator/validator_reports.jsonl`

## Reset seguro de checkpoint
1. Rode `python -m training.healthcheck`.
2. Se `concurso_ref` estiver fora do range:
   - ajuste checkpoint principal no banco para valor válido **ou**
   - apague apenas checkpoint incremental (`logs/checkpoint_incremental.json`) e deixe auto-resume rebasear.
3. Reinicie em modo seguro:
   - `python -m training.run_continuous --safe-default`

## Sinais de saúde esperados
- Logs de heartbeat pelo menos a cada ~15s.
- `GOVERNANCE` com `conf_raw` e `conf_ema` variando sem travar permanentemente.
- Resumo parcial com `totais_globais_14+` e `totais_globais_15` coerentes.
