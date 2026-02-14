@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Conferindo acertos pendentes
python -u training\user\check_hits_pending.py --auto
if errorlevel 1 (
  echo [ERRO] Falha ao conferir acertos pendentes.
  pause
  exit /b 1
)

pause
endlocal
