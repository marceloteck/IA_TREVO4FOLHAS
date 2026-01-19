-- =====================================================
-- 01) CONCURSOS (DADOS OFICIAIS)
-- dezenas em formato CSV: "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"
-- =====================================================
CREATE TABLE IF NOT EXISTS concursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso INTEGER UNIQUE NOT NULL,
    dezenas TEXT NOT NULL,
    data TEXT
);

CREATE INDEX IF NOT EXISTS idx_concursos_concurso ON concursos(concurso);

-- =====================================================
-- 02) TENTATIVAS / EXPERIMENTOS
-- =====================================================
CREATE TABLE IF NOT EXISTS tentativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso_n INTEGER NOT NULL,      -- N
    concurso_n1 INTEGER NOT NULL,     -- N+1 (resultado real usado na avaliação)
    tipo_jogo INTEGER NOT NULL,       -- 15 ou 18
    tentativa INTEGER NOT NULL,
    dezenas TEXT NOT NULL,
    acertos INTEGER NOT NULL,
    score REAL NOT NULL,
    score_tag TEXT NOT NULL,          -- ex: "hub_v3"
    brain_id TEXT,                    -- cerebro autor (quando aplicável)
    tempo_exec REAL,
    timestamp TEXT
);

CREATE INDEX IF NOT EXISTS idx_tentativas_concurso ON tentativas(concurso_n);
CREATE INDEX IF NOT EXISTS idx_tentativas_acertos ON tentativas(acertos);
CREATE INDEX IF NOT EXISTS idx_tentativas_score ON tentativas(score);

-- =====================================================
-- 03) MEMÓRIA DE JOGOS FORTES (11–15)
-- =====================================================
CREATE TABLE IF NOT EXISTS memoria_jogos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    concurso_n INTEGER NOT NULL,
    concurso_n1 INTEGER NOT NULL,
    dezenas TEXT NOT NULL,
    acertos INTEGER NOT NULL,
    peso REAL DEFAULT 1.0,
    origem TEXT,
    timestamp TEXT,
    UNIQUE(concurso_n, concurso_n1, dezenas)
);

CREATE INDEX IF NOT EXISTS idx_memoria_acertos ON memoria_jogos(acertos);

-- =====================================================
-- 04) CHECKPOINT INCREMENTAL (não reprocessar tudo)
-- =====================================================
CREATE TABLE IF NOT EXISTS checkpoint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_concurso_processado INTEGER,
    etapa TEXT,
    timestamp TEXT
);

-- =====================================================
-- 05) CÉREBROS (REGISTRO)
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
-- 06) ESTADO DOS CÉREBROS (JSON)
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_estado (
    cerebro_id INTEGER PRIMARY KEY,
    estado_json TEXT NOT NULL,
    atualizado_em TEXT,
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

-- =====================================================
-- 07) PERFORMANCE DO CÉREBRO POR CONCURSO
-- =====================================================
CREATE TABLE IF NOT EXISTS cerebro_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cerebro_id INTEGER NOT NULL,
    concurso INTEGER NOT NULL,
    media_pontos REAL,
    qtd_14 INTEGER,
    qtd_15 INTEGER,
    jogos_gerados INTEGER,
    atualizado_em TEXT,
    UNIQUE(cerebro_id, concurso),
    FOREIGN KEY (cerebro_id) REFERENCES cerebros(id)
);

-- =====================================================
-- 08) ESTATÍSTICAS CONSOLIDADAS (JSON)
-- =====================================================
CREATE TABLE IF NOT EXISTS estatisticas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,
    valor TEXT NOT NULL,
    ultima_atualizacao TEXT
);

-- =====================================================
-- 09) METADADOS DO SISTEMA
-- =====================================================
CREATE TABLE IF NOT EXISTS sistema (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave TEXT UNIQUE NOT NULL,
    valor TEXT NOT NULL
);

-- =====================================================
-- 10) LOGS LEVES
-- =====================================================
CREATE TABLE IF NOT EXISTS logs_execucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modulo TEXT,
    duracao REAL,
    timestamp TEXT
);
