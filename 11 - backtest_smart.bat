@echo off
setlocal enabledelayedexpansion

echo =========================================
echo   BACKTEST SMART (SEPARADO) - IA TREVO
echo =========================================

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
set STEPS=120
set MINUTES=0
set RECENT_WINDOW=220
set AVALIAR_TOP_K=40
set UCB_C=1.25

echo [INFO] steps         : %STEPS%
echo [INFO] minutes       : %MINUTES%
echo [INFO] recent_window : %RECENT_WINDOW%
echo [INFO] avaliar_top_k : %AVALIAR_TOP_K%
echo [INFO] ucb_c         : %UCB_C%
echo.

echo [RUN] Iniciando backtest inteligente (foco 14/15)...
python -m training.backtest.backtest_smart_engine --steps %STEPS% --minutes %MINUTES% --recent-window %RECENT_WINDOW% --avaliar-top-k %AVALIAR_TOP_K% --ucb-c %UCB_C%

if errorlevel 1 (
  echo.
  echo =========================================
  echo [ERRO] Falha ao executar backtest smart.
  echo Verifique o banco e rode START\startBD.py se necessario.
  echo =========================================
  pause
  exit /b 1
)

echo.
echo =========================================
echo [OK] Backtest smart concluido.
echo Veja progresso em: tabela backtest_smart_steps no banco.
echo =========================================

pause
endlocal
