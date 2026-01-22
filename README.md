# 🧠 IA_TREVO4FOLHAS — Inteligência Artificial para Lotofácil

Projeto de IA incremental e multicérebro para análise, aprendizado contínuo e geração consciente de jogos da Lotofácil, com foco estatístico real em 14 e 15 pontos.

---

## 📌 VISÃO GERAL

A IA funciona em 3 grandes pilares:

1. Treinamento incremental (N → N+1): Aprende a cada concurso novo.
2. Arquitetura multicérebro: 50+ cérebros especializados (Frequência, Atraso, Núcleo, Memória Elite, etc).
3. BrainHub (Meta-cérebro): Coordena e pondera quais cérebros são mais confiáveis no momento.

---

## 🗂️ ESTRUTURA DO PROJETO

IA_TREVO4FOLHAS/
├── START/
│   ├── startBD.py                # Inicialização do banco e histórico
│   ├── update_concursos.py       # Atualização de novos resultados
│   └── gerar_proximo_concurso.py # Motor de geração de jogos
├── training/
│   ├── trainer_v2.py             # Script de treino contínuo
│   ├── core/                     # Lógica base (BrainHub)
│   └── brains/                   # Modelos estatísticos e temporais
├── reports/                      # Relatórios de performance
└── GERAR_PROXIMO.bat             # Atalho para Windows

---

## ⚙️ INSTALAÇÃO E CONFIGURAÇÃO

1. Criar ambiente virtual:
   python -m venv venv

2. Ativar ambiente:
   Windows: venv\Scripts\activate
   Linux/Mac: source venv/bin/activate

3. Instalar dependências:
   pip install -r requirements.txt

4. Inicializar Banco de Dados (Obrigatório):
   python START/startBD.py

---

## 🧠 COMO UTILIZAR

### Atualizar Resultados
Sempre que houver um novo sorteio oficial:
python START/update_concursos.py

### Treinar a IA
Para a IA aprender os padrões mais recentes:
python -m training.trainer_v2          (Execução única)
python -m training.trainer_v2 --loop   (Treino contínuo 24/7)

### Gerar Jogos
Para gerar sugestões para o próximo concurso:
python START/gerar_proximo_concurso.py

Parâmetros úteis:
--perfil [conservador|balanceado|agressivo]
--both (Gera jogos de 15 e 18 dezenas)
--salvar-db (Registra os jogos para conferência futura)

---

## 📊 RELATÓRIOS
Para verificar o progresso do aprendizado e ranking dos cérebros:
python START/relatorio_aprendizado.py

---

## 🌐 DASHBOARD WEB

Para iniciar o painel web localmente:

```bash
python -m src.web_dashboard
```

O painel ficará disponível em `http://localhost:5000`.

### Executar via Windows (.bat)

```bat
start_dashboard.bat
```

### Alterar host/porta

Defina as variáveis de ambiente `HOST` e `PORT` antes de iniciar. Exemplos:

```bash
HOST=127.0.0.1 PORT=8000 python -m src.web_dashboard
```

```bat
set HOST=127.0.0.1
set PORT=8000
start_dashboard.bat
```

### Acesso online

Para expor o painel em rede, use um host acessível (ex: `0.0.0.0`) e libere a porta
no firewall/roteador ou use um túnel (ex: Cloudflare Tunnel, Ngrok). Em produção,
considere rodar atrás de um servidor WSGI (Gunicorn/Waitress) e configurar HTTPS.

--- 

⚠️ AVISO: Este software é uma ferramenta de estudo estatístico. Não garante lucros ou prêmios. O uso é de total responsabilidade do usuário.
