@echo off
setlocal enabledelayedexpansion

echo =====================================================
echo   BACKTEST SMART CONTINUO (AUTO-RELATORIO) - IA TREVO
echo =====================================================

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
REM ---------- PARAMETROS (PODE EDITAR) ----------
set STEPS=0
set MINUTES=0
set SUMMARY_EVERY=200
set PROGRESS_EVERY=10
set SAVE_EVERY=10

echo [INFO] steps          : %STEPS% (0 = infinito)
echo [INFO] minutes        : %MINUTES% (0 = sem limite de tempo)
echo [INFO] summary_every  : %SUMMARY_EVERY%
echo [INFO] progress_every : %PROGRESS_EVERY%
echo [INFO] save_every     : %SAVE_EVERY%
echo.

echo [RUN] Iniciando backtest smart continuo...
set CMD=python training/backtest/backtest_smart_engine.py --steps %STEPS% --minutes %MINUTES% --summary-every %SUMMARY_EVERY% --progress-every %PROGRESS_EVERY% --save-every %SAVE_EVERY%

echo [CMD] !CMD!
!CMD!

if errorlevel 1 (
  echo.
  echo =====================================================
  echo [ERRO] Falha ao executar backtest_smart_engine.py
  echo Dicas:
  echo  - Rode 2 - Start_bd.bat para garantir o banco
  echo  - Rode 6 - update_concursos.bat para atualizar concursos
  echo =====================================================
  pause
  exit /b 1
)

echo.
echo =====================================================
echo [OK] Execucao encerrada.
echo Se STEPS=0 e MINUTES=0, so termina quando voce parar (CTRL+C).
echo =====================================================

pause
endlocal
