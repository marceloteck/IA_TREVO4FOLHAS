@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
python -m desktop_app
if errorlevel 1 (
  echo [ERRO] Falha ao iniciar desktop_app.
  pause
  exit /b 1
)
endlocal
