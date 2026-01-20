@echo off
setlocal enabledelayedexpansion

REM =========================================
REM  BACKTEST 24x7 - IA TREVO (Windows)
REM  - replay N->N+1 infinito (exploração)
REM  - persiste no BD (tentativas + memoria_jogos + checkpoint_backtest)
REM =========================================

title BACKTEST 24x7 - IA TREVO

REM ---- Ir para a raiz do projeto (um nível acima de START) ----
cd /d "%~dp0.."

echo =========================================
echo   BACKTEST 24x7 - IA TREVO
echo =========================================

REM ---- Configs (ajuste se quiser) ----
set VENV_DIR=.venv
set LOG_DIR=logs
set LOG_FILE=%LOG_DIR%\backtest_24x7.log

REM Quantos concursos por "ciclo" (bloco)
set BLOCK_SIZE=500

REM Salvar estado do hub a cada N concursos
set SAVE_EVERY=10

REM Quantos candidatos avaliar por tamanho (custo)
set AVALIAR_TOP_K=40

REM Mínimo para salvar memória forte
set MIN_MEM=11

REM Seed (vazio = aleatório)
set SEED=

REM Modo agressivo: true/false
set AGGRESSIVE=false

REM Pausa quando termina um ciclo (segundos)
set SLEEP_AFTER_BLOCK=3

REM Pausa se der erro (segundos)
set SLEEP_ON_ERROR=20


REM ---- Preparar pasta de logs ----
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [INFO] Projeto: %CD%
echo [INFO] LOG: %LOG_FILE%
echo.

REM ---- Ativar venv ----
if exist "%VENV_DIR%\Scripts\activate.bat" (
  echo [OK] Ativando venv: %VENV_DIR%
  call "%VENV_DIR%\Scripts\activate.bat"
) else (
  echo [ERRO] Venv nao encontrada em "%VENV_DIR%".
  echo Crie sua venv assim:
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

REM ---- Loop infinito ----
:LOOP

echo.
echo ----------------------------------------- >> "%LOG_FILE%"
echo [%date% %time%] Ciclo iniciado >> "%LOG_FILE%"
echo ----------------------------------------- >> "%LOG_FILE%"

echo [RUN] Garantindo DB (schema + import CSV)...
python START\startBD.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERRO] startBD falhou. Veja log: %LOG_FILE%
  timeout /t %SLEEP_ON_ERROR% >nul
  goto LOOP
)

REM ---- Montar comando ----
set CMD=python -m training.backtest.backtest_engine --steps %BLOCK_SIZE% --save-every %SAVE_EVERY% --avaliar-top-k %AVALIAR_TOP_K% --min-mem %MIN_MEM%

if /I "%AGGRESSIVE%"=="true" (
  set CMD=!CMD! --aggressive
)

if not "%SEED%"=="" (
  set CMD=!CMD! --seed %SEED%
)

echo [RUN] !CMD!
echo [%date% %time%] RUN: !CMD! >> "%LOG_FILE%"

!CMD! >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERRO] Backtest falhou (vai reiniciar em %SLEEP_ON_ERROR%s). Veja log: %LOG_FILE%
  echo [%date% %time%] ERRO no backtest. Reiniciando... >> "%LOG_FILE%"
  timeout /t %SLEEP_ON_ERROR% >nul
  goto LOOP
)

echo [OK] Ciclo concluido. Pausa %SLEEP_AFTER_BLOCK%s...
echo [%date% %time%] Ciclo concluido OK. >> "%LOG_FILE%"
timeout /t %SLEEP_AFTER_BLOCK% >nul

goto LOOP
