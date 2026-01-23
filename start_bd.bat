@echo off
REM =====================================================
REM BAT - Inicializar Banco de Dados (Windows)
REM Projeto: IA_TREVO4FOLHAS
REM =====================================================

REM Garante que o BAT rode na pasta raiz do projeto
cd /d "%~dp0"

REM Ativar venv (se existir)
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

python START\startBD.py

echo.
pause
