# 🗺️ IA_TREVO4FOLHAS — Mapa técnico completo para programadores

Este documento foi criado para qualquer dev novo entrar no projeto, entender rapidamente a arquitetura, localizar problemas e saber **onde corrigir cada parte** sem quebrar o que já funciona.

---

## 1) Objetivo do projeto

O projeto implementa um pipeline de IA estatística para Lotofácil com:

- treino incremental `N -> N+1`,
- múltiplos cérebros especializados,
- BrainHub para seleção/consenso/diversidade,
- persistência em SQLite,
- geração de jogos para próximo concurso,
- dashboard e scripts operacionais.

---

## 2) Mapa de diretórios (alto nível)

## Raiz
- `README.md` → guia principal para uso.
- `README_MAPA_PROJETO.md` → este mapa técnico.
- `requirements.txt` → dependências Python.
- `desktop_app.py` → app desktop de orquestração.
- `*.bat` na raiz → atalhos Windows para operações principais.

## `START/` (operação)
- `startBD.py` → inicializa schema e base.
- `update_concursos.py` → atualiza concursos.
- `gerar_proximo_concurso.py` → geração de jogos para próximo concurso.
- `status_aprendizado.py` → radiografia do banco + cérebros + performance.

## `training/` (núcleo da IA)
- `trainer_v2.py` → treino incremental principal.
- `core/brain_hub.py` → BrainHub (score, consenso, diversidade, quotas).
- `core/base_brain.py` e `core/brain_interface.py` → contrato base dos cérebros.
- `brains/` → implementações de cérebros (estatísticos, heurísticos, estruturais, etc.).
- `backtest/backtest_engine.py` → motor de backtest (base, já existente).
- `backtest/backtest_smart_engine.py` → backtest inteligente separado (UCB + score temporal 14/15 + evolução de receitas + detecção de regime + banco de hipóteses).
- `fechamentos/` e `fechamentos_posicionais/` → geração de fechamentos.

## `data/`
- `database/db_schema.sql` → schema oficial do SQLite.
- `BD/` → banco principal e conexão.
- `planilhas/Lotofácil.csv` → fonte histórica.

## `src/`
- `web_dashboard.py` + `templates/` → dashboard web Flask.

## `scripts/`
- utilitários de avaliação, merge e relatórios.

## `tests/`
- suíte de testes automatizados (fluxo fechamentos, trainer helpers, catálogo por cérebro e backtest smart).

---

## 3) Fluxo funcional do sistema

1. **Base**: `START/startBD.py` cria tabelas e popula concursos.
2. **Atualização**: `START/update_concursos.py` traz novos concursos.
3. **Treino**: `python -m training.trainer_v2` processa `N -> N+1`.
4. **Persistência**:
   - checkpoint,
   - tentativas,
   - memória forte,
   - estado/performance por cérebro,
   - experimentos (quando habilitados).
5. **Geração próximo concurso**:
   - BrainHub + cérebros,
   - ranking e diversidade,
   - saída em `reports/` (incluindo modo por cérebro).

---

## 4) Onde corrigir cada tipo de problema

## A) Erro no treino incremental
- Arquivo foco: `training/trainer_v2.py`
- Pontos críticos:
  - checkpoint,
  - carregamento de cérebros,
  - geração 15/18,
  - persistência (tentativas/memória),
  - flags CLI.

## B) Cérebro não aparece / não gera jogos
- Verificar:
  - classe em `training/brains/...`,
  - registro no trainer (`trainer_v2.py`) ou builder heurístico,
  - se está `habilitado=1` na tabela `cerebros`,
  - se `evaluate_context` retorna > 0.

## C) Problema de ranking/diversidade
- Arquivo foco: `training/core/brain_hub.py`
- Ajustes comuns:
  - `exploration_rate`,
  - regras de consenso,
  - limite por cérebro (`max_brain_share` / quota),
  - `max_sim`/Jaccard.

## D) Erro de banco em ambiente legado
- Arquivos foco:
  - `data/database/db_schema.sql`,
  - `training/trainer_v2.py` (rotinas IF NOT EXISTS),
  - `START/status_aprendizado.py` (auto-criação de governança).

## E) Geração para usuário final
- Arquivo foco: `START/gerar_proximo_concurso.py`
- Recursos:
  - geração normal,
  - `--por-cerebro`,
  - `--por-cerebro-split-files`,
  - arquivos TXT com caminho absoluto.

## F) Dashboard
- Arquivo foco: `src/web_dashboard.py`
- Verificar rotas `/treinar`, `/gerar-jogos`, `/status/*`, `/logs/*`.

---

## 5) Comandos de diagnóstico rápido

```bash
# status completo da IA e banco
python START/status_aprendizado.py

# ajuda do trainer com flags disponíveis
python -m training.trainer_v2 --help

# ajuda do gerador (incluindo por-cerebro)
python START/gerar_proximo_concurso.py --help

# testes
pytest -q
```

---

## 6) Convenções para mudanças seguras

- Não remover cérebros antigos; preferir ON/OFF temporário.
- Novas tabelas sempre com `CREATE TABLE IF NOT EXISTS`.
- Toda nova heurística deve ter:
  - id único,
  - versão,
  - teste mínimo cobrindo comportamento esperado.
- Em mudanças de score/ranking:
  - sempre validar com backtest A/B,
  - registrar experimento com nome/versionamento.

---

## 7) Prompt detalhado de funcionamento (para alinhamento de time/IA)

Use o prompt abaixo para orientar devs/agentes sobre o comportamento esperado do sistema:

```text
Você está trabalhando no projeto IA_TREVO4FOLHAS.

Objetivo:
- Maximizar assertividade estatística no cenário Lotofácil sem quebrar estabilidade operacional.

Regras arquiteturais:
1) Não remover componentes existentes (cérebros, tabelas, fluxos); evoluir por extensão.
2) Treino incremental N->N+1 deve permanecer idempotente com checkpoint.
3) Persistência é obrigatória: tentativas, memória forte, estado de cérebro e performance por concurso.
4) Novas tabelas/recursos de governança devem ser criados com IF NOT EXISTS.
5) Qualquer otimização de seleção deve preservar diversidade e anti-colapso.

Fluxo de treino esperado:
- Carregar contexto recente.
- Registrar/instanciar cérebros ativos.
- Gerar candidatos 15/18 via BrainHub.
- Rankear, salvar tentativas, atualizar memória forte.
- Aprender por cérebro, salvar estado e checkpoint.

Fluxo de geração para usuário final:
- Permitir geração padrão e modo por cérebro.
- No modo por cérebro, listar jogos por cérebro top (q15/q14/média).
- Salvar TXT(s) de saída e informar caminho absoluto.

Política de melhoria:
- Preferir mudanças graduais e mensuráveis (A/B).
- Incluir flags CLI para ligar/desligar funcionalidades novas.
- Adicionar testes para cada comportamento novo.

Critérios de qualidade:
- Compatível com banco legado.
- Sem regressão em testes.
- Saída clara para usuário final (logs e caminhos de arquivo).
```

---

## 8) Checklist de release para programadores

- [ ] `pytest -q` passando.
- [ ] Sem quebrar CLI existente.
- [ ] Compatibilidade com DB legado garantida.
- [ ] README atualizado com novas flags.
- [ ] Relatórios e caminhos de saída claros.

