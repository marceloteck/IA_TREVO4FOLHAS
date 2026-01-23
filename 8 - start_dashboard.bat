@echo off
setlocal EnableExtensions

echo ============================================
echo IA_TREVO4FOLHAS - Dashboard Flask
echo ============================================

REM raiz do projeto
set ROOT_DIR=%~dp0

REM garante que o projeto esteja no PYTHONPATH
set PYTHONPATH=%ROOT_DIR%;%PYTHONPATH%

REM permite configurar host/porta via variaveis de ambiente
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=5000

echo.
echo Iniciando dashboard em http://%HOST%:%PORT%
echo.

python -m src.web_dashboard

if errorlevel 1 (
    echo.
    echo ❌ ERRO ao iniciar o Dashboard Flask
    pause
)

endlocal
