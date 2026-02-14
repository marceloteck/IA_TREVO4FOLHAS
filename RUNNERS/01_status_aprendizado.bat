@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul

if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Status do aprendizado
python -u START\status_aprendizado.py
if errorlevel 1 (
  echo [ERRO] Falha ao obter status do aprendizado.
  pause
  exit /b 1
)

pause
endlocal
