@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul

echo ============================================
echo IA_TREVO4FOLHAS - Dashboard Flask
echo ============================================

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrada. Usando Python do sistema...
)

set "PYTHONPATH=%cd%;%PYTHONPATH%"
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=5000

echo.
echo Iniciando dashboard em http://%HOST%:%PORT%
echo.

python -m src.web_dashboard
if errorlevel 1 (
    echo.
    echo [ERRO] Falha ao iniciar o Dashboard Flask.
    pause
    exit /b 1
)

endlocal
