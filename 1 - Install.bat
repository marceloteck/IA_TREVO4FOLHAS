@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul

echo =========================================
echo   INSTALADOR - IA LOTOFACIL
echo   Projeto: IA_TREVO4FOLHAS
echo =========================================

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado no PATH.
    echo Instale Python 3.10+ e marque "Add to PATH".
    pause
    exit /b 1
)

echo [OK] Python encontrado.

if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Criando ambiente virtual...
    python -m venv venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERRO] Nao foi possivel ativar a venv.
    pause
    exit /b 1
)

echo [INFO] Atualizando ferramentas base...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo [ERRO] Falha ao atualizar pip/setuptools/wheel.
    pause
    exit /b 1
)

echo [INFO] Instalando dependencias do projeto...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar requirements.txt.
    pause
    exit /b 1
)

echo [INFO] Preparando banco (schema + import CSV)...
python START\startBD.py
if errorlevel 1 (
    echo [ERRO] Falha ao inicializar banco.
    pause
    exit /b 1
)

echo [INFO] Atualizando concursos iniciais...
python START\update_concursos.py
if errorlevel 1 (
    echo [AVISO] Nao foi possivel atualizar concursos agora. Voce pode rodar "6 - update_concursos.bat" depois.
)

echo [INFO] Mostrando status inicial do aprendizado...
python START\status_aprendizado.py

echo =========================================
echo [OK] INSTALACAO CONCLUIDA
echo Agora rode: 13 - backtest_smart_continuo.bat
echo =========================================
pause
endlocal
