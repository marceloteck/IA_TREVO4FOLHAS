# 🧠 IA_TREVO4FOLHAS — Inteligência Artificial para Lotofácil

IA incremental e multicérebro para análise estatística, aprendizado contínuo e geração estruturada de jogos da Lotofácil, com foco em desempenho real nos cenários de 14 e 15 pontos.

---

## 📌 Visão geral

📘 Mapa técnico para programadores: `README_MAPA_PROJETO.md`

O sistema se organiza em três pilares principais:

1. **Treinamento incremental (N → N+1)**: aprende a cada concurso novo, sem reprocessar todo o histórico.
2. **Arquitetura multicérebro**: dezenas de cérebros especializados (frequência, atraso, núcleo, memória elite, heurísticas e estruturais).
3. **BrainHub (meta-cérebro)**: coordena relevância, diversidade e ranking dos candidatos entre os cérebros.

---

## ✨ Destaques

- **Geração estruturada**: combina padrões heurísticos e estatísticos (não é aleatoriedade pura).
- **Aprendizado persistente**: estados salvos no banco (`cerebro_estado`) e performance por concurso.
- **Diversidade controlada**: seleção final evita candidatos excessivamente similares.
- **Backtest e exploração**: replays históricos para avaliar cenários e ajustar parâmetros.
- **Dashboard web**: acompanhamento local via painel.

---

## 🗂️ Estrutura do projeto

```
IA_TREVO4FOLHAS/
├── START/                         # scripts de operação (BD, atualização e geração)
│   ├── startBD.py
│   ├── update_concursos.py
│   ├── gerar_proximo_concurso.py
│   └── status_aprendizado.py
├── training/
│   ├── trainer_v2.py              # treino incremental
│   ├── backtest/                  # motor de backtest
│   ├── core/                      # BrainHub e interfaces base
│   └── brains/                    # cérebros estatísticos/heurísticos/estruturais
├── data/                          # banco SQLite e artefatos
├── reports/                       # relatórios e métricas
├── scripts/                       # utilitários de avaliação e automação
└── src/                           # dashboard web
```

---

## ⚙️ Instalação e configuração

1. Criar ambiente virtual:
   ```bash
   python -m venv venv
   ```

2. Ativar ambiente:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

3. Instalar dependências:
   ```bash
   pip install -r requirements.txt
   ```

4. Inicializar o banco de dados (obrigatório):
   ```bash
   python START/startBD.py
   ```

---

## ▶️ Como utilizar

### 0) App desktop (sem .bat)

Agora você pode executar tudo via interface desktop em Python (sem remover os .bat).

```bash
python desktop_app.py
```

Funcionalidades disponíveis:
- Instalar/atualizar ambiente (venv + dependências + banco)
- Inicializar banco
- Atualizar concursos
- Treinar IA + backtest
- Gerar próximo concurso (configurável)
- Atualizar banco (merge)
- Status do aprendizado
- Iniciar dashboard

### 1) Atualizar resultados

```bash
python START/update_concursos.py
```

### 2) Treinar a IA

Execução única:
```bash
python -m training.trainer_v2
```

Treino contínuo (24/7):
```bash
python -m training.trainer_v2 --loop
```

### 3) Gerar jogos para o próximo concurso

```bash
python START/gerar_proximo_concurso.py
```

Parâmetros úteis:
- `--perfil [conservador|balanceado|agressivo]`
- `--both` (gera jogos de 15 e 18 dezenas)
- `--salvar-db` (registra os jogos no banco para conferência futura)

### 3.1) Catálogo por cérebro (usuário final)

Você pode gerar um catálogo com os **melhores cérebros por histórico 14/15**,
listando os jogos por cérebro (ex.: `per_brain=80`) para o usuário escolher qual cérebro usar.

```bash
python START/gerar_proximo_concurso.py --por-cerebro --size 15 --per-brain 80 --top-brains 12
```

Gerar também um TXT separado por cérebro (melhor visualização):

```bash
python START/gerar_proximo_concurso.py --por-cerebro --por-cerebro-split-files --size 15 --per-brain 80 --top-brains 12
```

Selecionar cérebros específicos:

```bash
python START/gerar_proximo_concurso.py --por-cerebro --brain-id struct_core_protect --brain-id stat_elite_memory
```

Atalho Windows (.bat):

```bat
10 - gerar_catalogo_por_cerebro.bat
```

Ao finalizar, o script informa no terminal o **caminho completo** dos arquivos `.txt` gerados.

---

## 🧠 BrainHub e cérebros

O BrainHub:
- avalia relevância de cada cérebro no contexto atual,
- coleta candidatos por cérebro,
- normaliza scores e aplica diversidade,
- registra aprendizado por desempenho.

### Novo cérebro: `heur_step_sequences`

Gerador estruturado baseado em **sequências de passos (delta sequences)**:

- Escolhe um número inicial.
- Aplica uma sequência de deltas (passos) com wrap 1..25.
- Faz “escape” de duplicatas (incremento com wrap).
- Permite mutação leve e exploração controlada.
- Aprende estatísticas simples por padrão (ex.: hits 13+, 14+).

### Cérebro experimental adicional: `heur_hotcold_balance_v1`

Baseado na teoria popular de dezenas “quentes/frias”:

- usa `recent_bias` mais baixo (aumenta chance de trazer dezenas menos recentes),
- mantém forma estatística mínima (paridade, soma, repetição e limite de sequência),
- objetivo: testar exploração sem quebrar estabilidade.

Parâmetros adicionais do `trainer_v2.py`:

```
--steps-mutation-rate 0.10
--steps-exploration-rate 0.10
--steps-delta-max 3
--steps-wrap-mode wrap
--steps-max-attempts-per-game 50

# auto-gestão de cérebros por performance
--auto-disable-min-games 3000
--auto-disable-keep-top-q15 20
--auto-disable-keep-top-q14 20
--auto-disable-recent-window 240
--auto-disable-recent-weight 0.70
# para desligar esse modo automático:
--disable-auto-manage-brains

# alocação dinâmica por cérebro (fase recente)
--dynamic-per-brain
--dynamic-per-brain-recent-window 180

# consenso forte / anti-colapso (opcionais)
--strong-consensus-enabled
--strong-consensus-bonus 0.01
--collapse-penalty-enabled
--collapse-penalty 0.01
--collapse-votes-threshold 5

# versionamento de experimento (A/B)
--experiment-name "ab_teste_brain_x_v1"
```

### Auto-gestão de cérebros (temporária)

Durante o treino, o `trainer_v2` pode ajustar a flag `habilitado` dos cérebros de forma automática:

- mantém habilitados os cérebros com melhor histórico (top por `q15` e `q14`),
- desabilita **temporariamente** cérebros com `q15=0` e volume alto de jogos,
- preserva cérebros de baixo volume (novos) para não matar exploração cedo.

Isso não remove cérebro algum do projeto; apenas alterna `ON/OFF` para priorizar assertividade.

### Governança de banco (criação dinâmica segura)

As tabelas de governança/experimentos são criadas com `CREATE TABLE IF NOT EXISTS`
durante execução do treino/status, evitando quebrar bancos antigos e sem sobrescrever
dados já existentes.

---

## 🔁 Backtest e exploração histórica

Motor de backtest (atual):
```bash
python -m training.backtest.backtest_engine --steps 100 --aggressive
```

Backtest inteligente separado (novo, sem alterar o atual):
```bash
python -m training.backtest.backtest_smart_engine --steps 120 --recent-window 220
```

Launcher Windows:
```bat
11 - backtest_smart.bat
12 - backtest_super_inteligente.bat
```

Parâmetros relevantes do smart:
- `--steps`: quantidade de concursos processados
- `--minutes`: limite por tempo
- `--recent-window`: janela para score temporal dos cérebros
- `--ucb-c`: intensidade de exploração do seletor adaptativo (UCB) para cenários (arms)
- `--recipe-ucb-c`: exploração do seletor adaptativo para receitas de cérebros
- `--recipe-evolve-every`: cria automaticamente nova receita (mistura/mutação) a cada N passos
- `--recipe-promote-reward`: limiar de promoção de receita
- `--recipe-min-pulls`: testes mínimos antes de promover/parkear receita
- `--revive-parked-every`: tenta reviver receitas parked quando o regime muda
- `--reward-q15` / `--reward-q14`: pesos da função de recompensa multiobjetivo
- `--avaliar-top-k`: número de candidatos avaliados por tamanho

Obs.: o smart mantém o modelo `N -> N+1`, usa os cérebros existentes e agora evolui “receitas” automaticamente (mantém, promove, parkear, revive), detecta regime (`estavel/volatil/aquecido/frio`) e registra hipóteses em `backtest_smart_hypotheses`.

---

## 📊 Relatórios e monitoramento

Status do aprendizado:
```bash
python START/status_aprendizado.py
```

Scripts auxiliares:
- `scripts/avaliar_desempenho.py`
- `scripts/gerar_dashboard_html.py`

---

## 🌐 Dashboard web

Iniciar o painel localmente:

```bash
python -m src.web_dashboard
```

O painel fica disponível em `http://localhost:5000`.

### Executar via Windows (.bat)

```bat
start_dashboard.bat
```

### Alterar host/porta

Defina `HOST` e `PORT` antes de iniciar:

```bash
HOST=127.0.0.1 PORT=8000 python -m src.web_dashboard
```

```bat
set HOST=127.0.0.1
set PORT=8000
start_dashboard.bat
```

### Acesso online

Para expor o painel em rede, use um host acessível (ex.: `0.0.0.0`) e libere a porta no firewall/roteador. Em produção, considere WSGI (Gunicorn/Waitress) e HTTPS.

---

## 🔒 Observação importante

Este software é uma ferramenta de estudo estatístico. **Não garante lucros ou prêmios**. O uso é de total responsabilidade do usuário.
