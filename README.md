# 🧠 IA_TREVO4FOLHAS — Inteligência Artificial para Lotofácil

IA incremental e multicérebro para análise estatística, aprendizado contínuo e geração estruturada de jogos da Lotofácil, com foco em desempenho real nos cenários de 14 e 15 pontos.

---

## 📌 Visão geral

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

Parâmetros adicionais do `trainer_v2.py`:

```
--steps-mutation-rate 0.10
--steps-exploration-rate 0.10
--steps-delta-max 3
--steps-wrap-mode wrap
--steps-max-attempts-per-game 50
```

---

## 🔁 Backtest e exploração histórica

Motor de backtest:
```bash
python -m training.backtest.backtest_engine --steps 100 --aggressive
```

Parâmetros relevantes:
- `--steps`: quantidade de concursos processados
- `--hours` / `--minutes`: limite por tempo
- `--avaliar-top-k`: número de candidatos avaliados por tamanho
- `--aggressive`: aumenta exploração e candidatos por cérebro

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
