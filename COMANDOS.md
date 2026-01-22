# Comandos via CMD (Windows/Linux/macOS)

Este arquivo concentra **tudo que pode ser executado via linha de comando** no projeto, incluindo instalação, treinamento, geração de jogos, status/memória, backtests, relatórios e dashboard.

> **Dica:** sempre rode os comandos a partir da raiz do projeto (`IA_TREVO4FOLHAS/`).

---

## 1) Instalação e preparação do ambiente

### Windows (atalho .bat)
```bat
install.bat
```

### Python (qualquer SO)
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
python START/startBD.py
```

---

## 2) Banco e atualização de concursos

### Inicializar/garantir banco (schema + import CSV)
```bash
python START/startBD.py
```

### Atualizar concursos (baixar resultados novos)
```bash
python START/update_concursos.py
```

### Windows (atalho .bat)
```bat
update_concursos.bat
```

### Merge de bancos temporários (utilitário)
```bash
python scripts/merge_temp_dbs.py
```

### Windows (atalho .bat)
```bat
update_bancoDeDAdos.bat
```

---

## 3) Treinamento (incremental / contínuo)

### Execução única
```bash
python -m training.trainer_v2
```

### Treino contínuo
```bash
python -m training.trainer_v2 --loop
```

### Windows (atalho .bat)
```bat
train_incremental.bat
```

---

## 4) Geração de jogos

### Geração padrão
```bash
python START/gerar_proximo_concurso.py
```

### Com parâmetros úteis
```bash
python START/gerar_proximo_concurso.py --perfil balanceado --both --salvar-db
```

### Windows (atalho .bat com parâmetros pré-configurados)
```bat
gerar_proximo_concurso.bat
```

---

## 5) Status da memória / aprendizado

### Status do aprendizado (banco + cérebros)
```bash
python START/status_aprendizado.py
```

### Windows (atalho .bat)
```bat
status_aprendizado.bat
```

---

## 6) Backtest e simulações

### Backtest 24x7 (loop infinito com logs)
```bat
backtest_24x7.bat
```

### Backtest rápido de teste (atalho)
```bat
trainer_incremental TESTE.bat
```

---

## 7) Avaliação e relatórios

### Avaliar desempenho (gera relatórios)
```bash
python scripts/avaliar_desempenho.py
```

### Ciclo automático: treina → avalia → ajusta → treina
```bash
python scripts/ciclo_treino_avalia.py --config config/ciclo_treino_avalia.json
```

### Gerar dashboard estático em HTML (a partir dos relatórios)
```bash
python scripts/gerar_dashboard_html.py
```

---

## 8) Dashboard web (Flask)

### Iniciar dashboard web
```bash
python -m src.web_dashboard
```

### Windows (atalho .bat)
```bat
start_dashboard.bat
```

---

## 9) Outros utilitários

### Marca commit “bom” (CI/automação)
```bash
python scripts/commit_if_good.py
```

