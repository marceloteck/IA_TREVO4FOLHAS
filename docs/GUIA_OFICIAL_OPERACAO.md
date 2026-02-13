# 🧠 IA_TREVO4FOLHAS — Guia Oficial de Operação

Sistema autônomo especialista em Lotofácil com:

- MetaController (MLP leve + Bandit)
- Reward 2.0
- Produção/Pesquisa
- Memory Gold / Quarantine
- Validador anti-overfit
- Telemetria completa
- Checkpoint automático
- Auto-tuning seguro
- Conferência pós-concurso
- Runners `.bat` para Windows

---

## 📂 Estrutura importante

- `RUNNERS/` → Execução rápida (`.bat`)
- `training/` → Código principal
- `config/` → Configurações ajustáveis
- `data/BD/` → Banco SQLite
- `data/models/` → Modelos salvos
- `logs/` → Logs de execução
- `reports/` → Relatórios HTML
- `exports/` → Jogos exportados ao usuário

---

## 🚀 Como usar no dia a dia (Windows)

Abra:

```bat
RUNNERS\MENU.bat
```

Você verá opções numeradas.

### 🔁 Fluxo normal (operacional real)

1. **Atualizar concursos**
   - Menu → `02_update_concursos.bat`
   - Insere resultados novos no banco.

2. **Conferir acertos dos jogos gerados**
   - Menu → `06_check_acertos.bat`
   - Verifica batches pendentes, confere hits, grava resultados, alimenta memória e pode disparar treino incremental.

3. **Gerar jogos para próximo concurso**
   - Produção (modo seguro): `04_generate_producao.bat`
   - Pesquisa (modo exploratório): `05_generate_pesquisa.bat`
   - Jogos ficam salvos no banco, exportados em `exports/` e rastreáveis por `batch_id`.

4. **Treino contínuo inteligente**
   - `03_backtest_smart_continuo.bat`
   - Usa checkpoint, retoma após queda de energia, alterna produção/pesquisa, aplica auto-tuning e salva telemetria.

5. **Gerar relatório**
   - `08_report.bat`
   - Cria `reports/run_<id>.html`.

6. **Rodar limpeza de memória**
   - `07_memory_refiner.bat`
   - Separa em Gold / Quarantine / Audit.

7. **Modo automático completo (recomendado)**
   - `09_auto_pos_concurso.bat`
   - Fluxo: update concursos → conferir acertos → treinar incrementalmente → atualizar memória.

---

## 🧠 Modos do sistema

### 🟢 Produção

- Conservador
- Usa Gold preferencialmente
- Baixa exploração
- Portfólio mais estruturado

### 🟠 Pesquisa

- Mais exploração
- Slots experimentais
- Testes A/B
- Promoção só se bater baseline

Troca automática baseada em regime, estagnação e performance recente.

---

## 💾 Queda de energia

O sistema salva:

- estado do MetaController
- estado do Bandit
- modo atual
- estagnação
- experimentos
- RNG
- step atual

Ao rodar novamente, retoma do último checkpoint válido.

---

## 🏆 Memória

- **Bruta**: tudo que já foi aprendido.
- **Gold**: exemplos confiáveis e de qualidade.
- **Quarantine**: possível ruído/overfit.

Produção usa Gold prioritariamente quando disponível.

---

## 📊 Relatórios importantes

No HTML da run:

- reward médio
- total 14+
- total 15
- diversidade média
- fallback rate
- taxa produção/pesquisa
- top arms/recipes
- tamanho Gold/Quarantine
- experimentos aprovados

---

## ⚙️ Ajustes manuais (opcional)

Arquivos em `config/`:

- `meta_controller.json`
- `reward_v2.json`
- `production_research.json`
- `portfolio.json`
- `validator.json`
- `memory_refiner.json`
- `performance.json`
- `auto_tuning.json`

> Recomendação: manter o AutoTuner ativo com limites padrão.

---

## 🔄 Manutenção recomendada

- Rodar Memory Refiner semanalmente.
- Gerar relatório semanal.
- Verificar tamanho da Gold.
- Fazer backup periódico do banco.

---

## ✅ Status operacional esperado

Você terá:

- sistema autônomo
- aprendizado incremental
- controle de overfit
- auto-tuning
- modo produção/pesquisa
- persistência total
- operação via `.bat`
- telemetria profissional
- ciclo fechado real (gerar → conferir → aprender)
