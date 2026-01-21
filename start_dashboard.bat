@echo off
setlocal

echo ============================================
echo IA_TREVO4FOLHAS - Dashboard Flask
echo ============================================

REM Garante que o projeto esteja no PYTHONPATH
set PYTHONPATH=%~dp0

REM Inicia o navegador em uma nova janela após 3 segundos de espera
start /b cmd /c "timeout /t 3 >nul && start http://127.0.0.1:5000"

echo Iniciando o servidor Flask...
echo O painel sera aberto no seu navegador em instantes.
echo.

REM Executa o Python (este comando bloqueia o terminal)
python -m src.web_dashboard

endlocal