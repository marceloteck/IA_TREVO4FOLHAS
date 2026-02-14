@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul

if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Atualizando concursos
python START\update_concursos.py
if errorlevel 1 (
  echo [ERRO] Falha ao atualizar concursos.
  pause
  exit /b 1
)

pause
endlocal
