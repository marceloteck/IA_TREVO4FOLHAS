@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Gerando jogos (pesquisa)
python -u training\user\generate_for_user.py --mode research
if errorlevel 1 (
  echo [ERRO] Falha ao gerar jogos de pesquisa.
  pause
  exit /b 1
)

pause
endlocal
