@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"

chcp 65001 >nul

if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrada. Use "1 - Install.bat" primeiro.
)

echo ====================================
echo RUNNER - BACKTEST SMART CONTINUO
echo ====================================
echo [INFO] Aprendizado em tempo real ativo.
echo [INFO] Para parar manualmente, use CTRL+C.
echo.

python -u -m training.backtest.backtest_smart_engine --steps 0 --minutes 0 --progress-every 5 --summary-every 50 --save-every 10 --run-name runner_continuo

if errorlevel 1 (
  echo.
  echo [ERRO] O runner falhou durante a execucao.
  echo [DICA] Rode: 1 - Install.bat ^| 2 - Start_bd.bat ^| 6 - update_concursos.bat
  pause
  exit /b 1
)

echo.
echo [OK] Runner finalizado.
pause
endlocal
