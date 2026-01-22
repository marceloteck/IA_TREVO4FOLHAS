@echo off
setlocal

echo ============================================
echo IA_TREVO4FOLHAS - Dashboard Flask
echo ============================================

REM garante que o projeto esteja no PYTHONPATH
set PYTHONPATH=%~dp0

REM permite configurar host/porta via variaveis de ambiente
if "%HOST%"=="" set HOST=0.0.0.0
if "%PORT%"=="" set PORT=5000

python -m src.web_dashboard

endlocal
