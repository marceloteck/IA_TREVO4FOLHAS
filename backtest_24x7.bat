@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ==========================
REM CONFIG (edite aqui)
REM ==========================
set "VENV_DIR=.venv"
set "LOG_FILE=logs\treino.log"

set "BLOCK_SIZE=200"
set "SAVE_EVERY=50"
set "AVALIAR_TOP_K=60"
set "MIN_MEM=1000"

set "AGGRESSIVE=false"
set "SEED="

set "SLEEP_SECONDS=10"
set "SLEEP_ON_ERROR=30"

REM ==========================
REM Preparar pasta de logs
REM ==========================
for %%D in ("%LOG_FILE%") do if not exist "%%~dpD" mkdir "%%~dpD" >nul 2>&1

REM ==========================
REM Ativar venv (se existir)
REM ==========================
if exist "%VENV_DIR%\Scripts\activate.bat" (
  echo [OK] Ativando venv: %VENV_DIR%
  call "%VENV_DIR%\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado em "%VENV_DIR%". Rodando com Python do sistema...
)

REM ==========================
REM Loop infinito
REM ==========================
:LOOP

echo.>>"%LOG_FILE%"
echo ----------------------------------------- >> "%LOG_FILE%"
echo [%date% %time%] Ciclo iniciado >> "%LOG_FILE%"
echo ----------------------------------------- >> "%LOG_FILE%"

echo [RUN] Garantindo DB (schema + import CSV)...
python "START\startBD.py" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERRO] startBD falhou. Veja log: %LOG_FILE%
  echo [%date% %time%] ERRO: startBD falhou >> "%LOG_FILE%"
  timeout /t %SLEEP_ON_ERROR% >nul
  goto LOOP
)

REM ==========================
REM Montar comando do treino
REM ==========================
set "CMD=python -m training.backtest.backtest_engine --steps %BLOCK_SIZE% --save-every %SAVE_EVERY% --avaliar-top-k %AVALIAR_TOP_K% --min-mem %MIN_MEM%"

if /I "%AGGRESSIVE%"=="true" set "CMD=!CMD! --aggressive"
if not "%SEED%"=="" set "CMD=!CMD! --seed %SEED%"

echo [RUN] !CMD!
echo [%date% %time%] RUN: !CMD!>>"%LOG_FILE%"

call !CMD! >> "%LOG_FILE%" 2>&1
set "EXITCODE=!errorlevel!"

if not "!EXITCODE!"=="0" (
  echo [ERRO] treino falhou (exit=!EXITCODE!). Veja log: %LOG_FILE%
  echo [%date% %time%] ERRO: treino falhou (exit=!EXITCODE!)>>"%LOG_FILE%"
  timeout /t %SLEEP_ON_ERROR% >nul
  goto LOOP
)

echo [OK] Ciclo finalizado. Aguardando %SLEEP_SECONDS%s...
echo [%date% %time%] OK: ciclo finalizado>>"%LOG_FILE%"
timeout /t %SLEEP_SECONDS% >nul
goto LOOP
