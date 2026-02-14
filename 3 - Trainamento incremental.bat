@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul

echo =========================================
echo Treinamento Incremental + Backtest
echo Projeto: IA_TREVO4FOLHAS
echo =========================================

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrada. Usando Python do sistema...
)

echo.
echo [ETAPA 1/2] Treinamento incremental...
python -m training.trainer_v2
if errorlevel 1 (
  echo [ERRO] Falha no treinamento incremental.
  pause
  exit /b 1
)

echo.
echo [ETAPA 2/2] Backtest com progresso visivel...
python -m training.backtest.backtest_engine --hours 5 --block-size 150 --min-mem 11 --aggressive
if errorlevel 1 (
  echo [ERRO] Falha no backtest.
  pause
  exit /b 1
)

echo.
echo [OK] Fluxo incremental concluido.
pause
endlocal
