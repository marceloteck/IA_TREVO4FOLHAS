@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

chcp 65001 >nul

echo =====================================================
echo   BACKTEST SMART CONTINUO (APRENDIZADO EM TEMPO REAL)
echo =====================================================

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
REM ---------- PARAMETROS ----------
set STEPS=0
set MINUTES=0
set SUMMARY_EVERY=50
set PROGRESS_EVERY=5
set SAVE_EVERY=10
set RUN_NAME=smart_continuo

echo [INFO] steps          : %STEPS% (0 = infinito)
echo [INFO] minutes        : %MINUTES% (0 = sem limite)
echo [INFO] progress_every : %PROGRESS_EVERY% (mostra pensamento/aprendizado)
echo [INFO] summary_every  : %SUMMARY_EVERY% (resumo por cerebro)
echo [INFO] save_every     : %SAVE_EVERY% (checkpoint)
echo [INFO] run_name       : %RUN_NAME%
echo.
echo [DICA] Enquanto roda, abra tambem: 7 - status_aprendizado.bat

echo.
echo [RUN] Iniciando treinamento continuo da super inteligencia...
set "CMD=python -m training.backtest.backtest_smart_engine --steps %STEPS% --minutes %MINUTES% --summary-every %SUMMARY_EVERY% --progress-every %PROGRESS_EVERY% --save-every %SAVE_EVERY% --run-name %RUN_NAME%"

echo [CMD] !CMD!
!CMD!

if errorlevel 1 (
  echo.
  echo =====================================================
  echo [ERRO] Falha ao executar backtest_smart_engine.py
  echo Dicas:
  echo  - Rode 1 - Install.bat
  echo  - Rode 2 - Start_bd.bat e 6 - update_concursos.bat
  echo =====================================================
  pause
  exit /b 1
)

echo.
echo =====================================================
echo [OK] Execucao encerrada.
echo Com STEPS=0 e MINUTES=0, so termina com CTRL+C.
echo =====================================================
pause
endlocal
