@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Gerando jogos (producao)
python -u training\user\generate_for_user.py --mode production
if errorlevel 1 (
  echo [ERRO] Falha ao gerar jogos de producao.
  pause
  exit /b 1
)

pause
endlocal
