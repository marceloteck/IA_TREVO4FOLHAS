@echo off
setlocal

echo ============================================
echo IA_TREVO4FOLHAS - Dashboard Flask
echo ============================================

REM garante que o projeto esteja no PYTHONPATH
set PYTHONPATH=%~dp0

python -m src.web_dashboard

endlocal
