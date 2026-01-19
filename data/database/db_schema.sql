-- =====================================================
-- 01) CONCURSOS (DADOS OFICIAIS) - d1..d15
-- =====================================================
CREATE TABLE IF NOT EXISTS concursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso INTEGER UNIQUE NOT NULL,
    d1  INTEGER NOT NULL,
    d2  INTEGER NOT NULL,
    d3  INTEGER NOT NULL,
    d4  INTEGER NOT NULL,
    d5  INTEGER NOT NULL,
    d6  INTEGER NOT NULL,
    d7  INTEGER NOT NULL,
    d8  INTEGER NOT NULL,
    d9  INTEGER NOT NULL,
    d10 INTEGER NOT NULL,
    d11 INTEGER NOT NULL,
    d12 INTEGER NOT NULL,
    d13 INTEGER NOT NULL,
    d14 INTEGER NOT NULL,
    d15 INTEGER NOT NULL,
    data TEXT
);
CREATE INDEX IF NOT EXISTS idx_concursos_concurso ON concursos(concurso);

-- =====================================================
-- 02) FREQUENCIAS (cache consolidado opcional)
-- =====================================================
CREATE TABLE IF NOT EXISTS frequencias (
    numero INTEGER PRIMARY KEY,
    quantidade INTEGER NOT NULL,
    peso REAL NOT NULL,
    atualizado_em TEXT
);

-- =====================================================
-- 03) CHECKPOINT INCREMENTAL (não reprocessar tudo)
-- =====================================================
CREATE TABLE IF NOT EXISTS checkpoint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_concurso_processado INTEGER,
    etapa TEXT,
    timestamp TEXT
);

-- =====================================================
-- 04) TENTATIVAS / EXPERIMENTOS (auditoria do treino)
-- =====================================================
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso_n INTEGER NOT NULL,
    concurso_n1 INTEGER NOT NULL,
    tipo_jogo INTEGER NOT NULL,      -- 15 ou 18
    tentativa INTEGER NOT NULL,
    d1  INTEGER, d2  INTEGER, d3  INTEGER, d4  INTEGER, d5  INTEGER,
    d6  INTEGER, d7  INTEGER, d8  INTEGER, d9  INTEGER, d10 INTEGER,
    d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
    d16 INTEGER, d17 INTEGER, d18 INTEGER, -- para jogos 18
    acertos INTEGER NOT NULL,
    score REAL NOT NULL,
    score_tag TEXT NOT NULL,
    brain_id TEXT,
    tempo_exec REAL,
    timestamp TEXT
);
CREATE INDEX IF NOT EXISTS idx_tentativas_concurso ON tentativas(concurso_n);
CREATE INDEX IF NOT EXISTS idx_tentativas_acertos ON tentativas(acertos);
CREATE INDEX IF NOT EXISTS idx_tentativas_score   ON tentativas(score);

-- =====================================================
-- 05) MEMÓRIA DE JOGOS FORTES (11–15) - persistência real
-- =====================================================
CREATE TABLE IF NOT EXISTS memoria_jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso_n INTEGER NOT NULL,
    concurso_n1 INTEGER NOT NULL,
    tipo_jogo INTEGER NOT NULL,
    d1  INTEGER, d2  INTEGER, d3  INTEGER, d4  INTEGER, d5  INTEGER,
    d6  INTEGER, d7  INTEGER, d8  INTEGER, d9  INTEGER, d10 INTEGER,
    d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
    d16 INTEGER, d17 INTEGER, d18 INTEGER,
    acertos INTEGER NOT NULL,
    peso REAL DEFAULT 1.0,
    origem TEXT,
    timestamp TEXT,
    UNIQUE(concurso_n, concurso_n1, tipo_jogo,
           d1,d2,d3,d4,d5,d6,d7,d8,d9,d10,d11,d12,d13,d14,d15,d16,d17,d18)
);
CREATE INDEX IF NOT EXISTS idx_memoria_acertos ON memoria_jogos(acertos);

-- =====================================================
-- 06) CÉREBROS (REGISTRO)
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brain_id TEXT UNIQUE NOT NULL,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    versao TEXT NOT NULL,
    habilitado INTEGER DEFAULT 1,
    criado_em TEXT,
    atualizado_em TEXT
);

-- =====================================================
-- 07) ESTADO DOS CÉREBROS (JSON)
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_estado (
    cerebro_id INTEGER PRIMARY KEY,
    estado_json TEXT NOT NULL,
    atualizado_em TEXT,
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

-- =====================================================
-- 08) PERFORMANCE DO CÉREBRO POR CONCURSO
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cerebro_id INTEGER NOT NULL,
    concurso INTEGER NOT NULL,
    jogos_gerados INTEGER DEFAULT 0,
    media_pontos REAL DEFAULT 0,
    qtd_11 INTEGER DEFAULT 0,
    qtd_12 INTEGER DEFAULT 0,
    qtd_13 INTEGER DEFAULT 0,
    qtd_14 INTEGER DEFAULT 0,
    qtd_15 INTEGER DEFAULT 0,
    atualizado_em TEXT,
    UNIQUE(cerebro_id, concurso),
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

-- =====================================================
-- 09) ESTATÍSTICAS CONSOLIDADAS (JSON)
-- =====================================================
CREATE TABLE IF NOT EXISTS estatisticas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,
    valor TEXT NOT NULL,
    ultima_atualizacao TEXT
);

-- =====================================================
-- 10) METADADOS DO SISTEMA
-- =====================================================
CREATE TABLE IF NOT EXISTS sistema (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,
    valor TEXT NOT NULL
);

-- =====================================================
-- 11) LOGS LEVES
-- =====================================================
CREATE TABLE IF NOT EXISTS logs_execucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo TEXT,
    duracao REAL,
    timestamp TEXT
);
