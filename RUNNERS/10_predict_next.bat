@echo off
setlocal EnableExtensions
chcp 65001 >nul

REM =========================
REM Configuracoes (edite aqui)
REM =========================
set "TIPO=15"
set "MAX_JOGOS=30"
set "POOL_SIZE=18"
set "DRYRUN=1"
set "SEED="

REM =========================
REM Paths
REM =========================
set "ROOT=%~dp0.."
set "SCRIPT=%ROOT%\training\backtest\backtest_v2_predict_next.py"

if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
if not exist "%ROOT%\exports" mkdir "%ROOT%\exports"

REM =========================
REM Timestamp (WMIC com fallback)
REM =========================
set "DT="
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set "DT=%%I"

if defined DT (
    set "TS=%DT:~0,4%-%DT:~4,2%-%DT:~6,2%_%DT:~8,2%-%DT:~10,2%-%DT:~12,2%"
) else (
    set "D=%DATE%"
    set "T=%TIME%"
    set "D=%D:/=-%"
    set "D=%D:.=-%"
    set "D=%D: =0%"
    set "T=%T::=-%"
    set "T=%T:.=-%"
    set "T=%T: =0%"
    set "TS=%D%_%T%"
)

set "LOG=%ROOT%\logs\predict_next_%TS%.log"

echo ====================================
echo PREVER PROXIMO CONCURSO (BACKTEST_V2)
echo ====================================
echo ROOT  : %ROOT%
echo SCRIPT: %SCRIPT%
echo LOG   : %LOG%
echo.

echo [INFO] Iniciando runner... > "%LOG%"
echo [INFO] Params base: --tipo %TIPO% --max-jogos %MAX_JOGOS% --pool-size %POOL_SIZE% >> "%LOG%"
if "%DRYRUN%"=="1" echo [INFO] Modo dry-run habilitado >> "%LOG%"
if defined SEED echo [INFO] Seed fixa: %SEED% >> "%LOG%"

if not exist "%ROOT%\venv\Scripts\activate.bat" (
    echo [ERRO] venv nao encontrado em "%ROOT%\venv\Scripts\activate.bat"
    echo [ERRO] Crie/ative o ambiente virtual antes de rodar.
    echo [ERRO] venv nao encontrado. >> "%LOG%"
    pause
    exit /b 1
)

call "%ROOT%\venv\Scripts\activate.bat" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERRO] Falha ao ativar venv.
    echo [ERRO] Falha ao ativar venv. >> "%LOG%"
    pause
    exit /b 1
)

if "%DRYRUN%"=="1" (
    if defined SEED (
        echo [INFO] Executando com --dry-run e --seed %SEED% >> "%LOG%"
        python "%SCRIPT%" --tipo %TIPO% --max-jogos %MAX_JOGOS% --pool-size %POOL_SIZE% --dry-run --seed %SEED% >> "%LOG%" 2>&1
    ) else (
        echo [INFO] Executando com --dry-run >> "%LOG%"
        python "%SCRIPT%" --tipo %TIPO% --max-jogos %MAX_JOGOS% --pool-size %POOL_SIZE% --dry-run >> "%LOG%" 2>&1
    )
) else (
    if defined SEED (
        echo [INFO] Executando com --seed %SEED% >> "%LOG%"
        python "%SCRIPT%" --tipo %TIPO% --max-jogos %MAX_JOGOS% --pool-size %POOL_SIZE% --seed %SEED% >> "%LOG%" 2>&1
    ) else (
        echo [INFO] Executando sem dry-run >> "%LOG%"
        python "%SCRIPT%" --tipo %TIPO% --max-jogos %MAX_JOGOS% --pool-size %POOL_SIZE% >> "%LOG%" 2>&1
    )
)

set "RC=%ERRORLEVEL%"
echo. >> "%LOG%"
echo [INFO] Return code: %RC% >> "%LOG%"

if "%RC%"=="0" (
    echo OK: predição gerada. Veja exports/ e logs/
    echo [OK] Predicao gerada com sucesso. >> "%LOG%"
) else (
    echo [ERRO] Falha na execucao. Consulte o log:
    echo %LOG%
    echo [ERRO] Falha na execucao. >> "%LOG%"
)

echo.
echo Log completo: %LOG%
pause
exit /b %RC%
