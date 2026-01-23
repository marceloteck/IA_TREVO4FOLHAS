@echo off
echo =========================================
echo BAT - Inicializar Banco de Dados
echo Projeto: IA_TREVO4FOLHAS
echo =========================================

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
