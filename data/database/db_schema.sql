-- =====================================================
-- TABELA 01 — CONCURSOS OFICIAIS (FONTE DA VERDADE)
-- =====================================================
CREATE TABLE IF NOT EXISTS concursos (
    concurso INTEGER PRIMARY KEY,
    d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER,
    d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
    d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
    data TEXT
);

CREATE INDEX IF NOT EXISTS idx_concursos_data
ON concursos(data);

-- =====================================================
-- TABELA 02 — CÉREBROS (ENTIDADES DE APRENDIZADO)
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    tipo TEXT NOT NULL,              -- statistical | pattern | hybrid | neural
    classe TEXT NOT NULL,            -- classe Python
    versao TEXT NOT NULL,
    ativo INTEGER DEFAULT 1,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cerebros_tipo
ON cerebros(tipo);

-- =====================================================
-- TABELA 03 — ESTADO INTERNO DOS CÉREBROS (MEMÓRIA VIVA)
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_estado (
    cerebro_id INTEGER PRIMARY KEY,
    estado_json TEXT NOT NULL,       -- JSON serializado
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

-- =====================================================
-- TABELA 04 — JOGOS GERADOS PELOS CÉREBROS
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cerebro_id INTEGER NOT NULL,
    concurso INTEGER NOT NULL,
    tamanho_jogo INTEGER NOT NULL,   -- 15 ou 18
    jogo TEXT NOT NULL,              -- JSON: [1,2,3,...]
    pontos INTEGER,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id),
    FOREIGN KEY (concurso) REFERENCES concursos(concurso)
);

CREATE INDEX IF NOT EXISTS idx_cerebro_jogos_cerebro
ON cerebro_jogos(cerebro_id);

CREATE INDEX IF NOT EXISTS idx_cerebro_jogos_pontos
ON cerebro_jogos(pontos);

-- =====================================================
-- TABELA 05 — PERFORMANCE CONSOLIDADA DOS CÉREBROS
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cerebro_id INTEGER NOT NULL,
    concurso INTEGER NOT NULL,
    jogos_gerados INTEGER,
    media_pontos REAL,
    max_pontos INTEGER,
    qtd_11 INTEGER,
    qtd_12 INTEGER,
    qtd_13 INTEGER,
    qtd_14 INTEGER,
    qtd_15 INTEGER,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

CREATE INDEX IF NOT EXISTS idx_cerebro_performance_cerebro
ON cerebro_performance(cerebro_id);

CREATE INDEX IF NOT EXISTS idx_cerebro_performance_max
ON cerebro_performance(max_pontos);

-- =====================================================
-- TABELA 06 — CHECKPOINT GLOBAL DE TREINAMENTO
-- =====================================================
CREATE TABLE IF NOT EXISTS checkpoint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_concurso_processado INTEGER,
    ultima_execucao TEXT,
    atualizado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- TABELA 07 — METADADOS DO SISTEMA
-- =====================================================
CREATE TABLE IF NOT EXISTS sistema (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- =====================================================
-- TABELA 08 — LOGS DE EXECUÇÃO (LEVE E OPCIONAL)
-- =====================================================
CREATE TABLE IF NOT EXISTS logs_execucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo TEXT,
    mensagem TEXT,
    duracao REAL,
    criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
);
