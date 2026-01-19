-- =====================================================
-- TABELA 01 — CONCURSOS OFICIAIS (DADOS BRUTOS)
-- =====================================================
CREATE TABLE IF NOT EXISTS concursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso INTEGER UNIQUE NOT NULL,
    dezenas TEXT NOT NULL,          -- ex: "01,02,03,..."
    data TEXT
);

CREATE INDEX IF NOT EXISTS idx_concursos_numero
ON concursos(concurso);

-- =====================================================
-- TABELA 02 — TENTATIVAS DA IA (EXPERIMENTOS)
-- =====================================================
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso INTEGER NOT NULL,
    tipo_jogo INTEGER NOT NULL,      -- 15 ou 18 dezenas
    tentativa INTEGER NOT NULL,
    dezenas TEXT NOT NULL,
    acertos INTEGER NOT NULL,
    score REAL NOT NULL,
    versao_score TEXT NOT NULL,      -- ex: "1415_v2"
    tempo_exec REAL,
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_tentativas_concurso
ON tentativas(concurso);

CREATE INDEX IF NOT EXISTS idx_tentativas_acertos
ON tentativas(acertos);

CREATE INDEX IF NOT EXISTS idx_tentativas_score
ON tentativas(score);

-- =====================================================
-- TABELA 03 — MEMÓRIA DE JOGOS FORTES (11–15 PONTOS)
-- =====================================================
CREATE TABLE IF NOT EXISTS memoria_jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso INTEGER NOT NULL,
    dezenas TEXT NOT NULL,
    acertos INTEGER NOT NULL,
    peso REAL DEFAULT 1.0,           -- peso estatístico
    origem TEXT,                     -- real / simulado
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_memoria_acertos
ON memoria_jogos(acertos);

-- =====================================================
-- TABELA 04 — ESTATÍSTICAS CONSOLIDADAS
-- =====================================================
CREATE TABLE IF NOT EXISTS estatisticas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,      -- ex: "freq_global"
    valor TEXT NOT NULL,             -- JSON serializado
    ultima_atualizacao TEXT
);

-- =====================================================
-- TABELA 05 — CHECKPOINT DE TREINAMENTO INCREMENTAL
-- =====================================================
CREATE TABLE IF NOT EXISTS checkpoint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_concurso_processado INTEGER,
    ultimo_treino TEXT,              -- ex: "frequencia", "memoria"
    timestamp TEXT
);

-- =====================================================
-- TABELA 06 — METADADOS DO SISTEMA
-- =====================================================
CREATE TABLE IF NOT EXISTS sistema (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,
    valor TEXT NOT NULL
);

-- =====================================================
-- TABELA 07 — LOG DE PERFORMANCE (LEVE)
-- =====================================================
CREATE TABLE IF NOT EXISTS logs_execucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo TEXT,
    duracao REAL,
    timestamp TEXT
);
