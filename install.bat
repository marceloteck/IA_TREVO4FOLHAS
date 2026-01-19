@echo off
cls

echo =========================================
echo   INSTALADOR - IA LOTOFACIL (WINDOWS)
echo =========================================
echo.

REM ================================
REM 1. VERIFICAR PYTHON
REM ================================
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo ❌ Python nao encontrado.
    echo 👉 Instale Python 3.10+ e marque "Add to PATH"
    pause
    exit /b 1
)

echo ✅ Python encontrado.
echo.

REM ================================
REM 2. CRIAR AMBIENTE VIRTUAL
REM ================================
IF NOT EXIST venv (
    echo 📦 Criando ambiente virtual...
    python -m venv venv
    IF ERRORLEVEL 1 (
        echo ❌ Falha ao criar ambiente virtual.
        pause
        exit /b 1
    )
) ELSE (
    echo 📦 Ambiente virtual ja existe.
)

echo.

REM ================================
REM 3. ATIVAR VENV
REM ================================
call venv\Scripts\activate
IF ERRORLEVEL 1 (
    echo ❌ Falha ao ativar ambiente virtual.
    pause
    exit /b 1
)

echo ✅ Ambiente virtual ativado.
echo.

REM ================================
REM 4. ATUALIZAR PIP
REM ================================
echo 🔄 Atualizando pip...
python -m pip install --upgrade pip
echo.

REM ================================
REM 5. INSTALAR DEPENDENCIAS
REM ================================
echo 📥 Instalando dependencias...
pip install -r requirements.txt
IF ERRORLEVEL 1 (
    echo ❌ Erro ao instalar dependencias.
    pause
    exit /b 1
)

echo ✅ Dependencias instaladas.
echo.

REM ================================
REM 6. INICIALIZAR BANCO DE DADOS
REM ================================
IF NOT EXIST data\BD\lotofacil.db (
    echo 🗄️ Inicializando banco de dados...
    python START/startBD.py
    IF ERRORLEVEL 1 (
        echo ❌ Erro ao inicializar banco de dados.
        pause
        exit /b 1
    )
) ELSE (
    echo 🗄️ Banco de dados ja existe. Pulando inicializacao.
)

echo.
echo =========================================
echo ✅ INSTALACAO CONCLUIDA COM SUCESSO
echo =========================================
echo.
pause
