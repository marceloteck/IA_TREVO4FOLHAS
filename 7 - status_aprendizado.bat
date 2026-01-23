@echo off
echo =========================================
echo   STATUS DO APRENDIZADO (BANCO / CEREBROS)
echo =========================================
echo.

REM Ativar venv (se existir)
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call venv\Scripts\activate
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.


python START\status_aprendizado.py

echo =========================================
echo   FINALIZADO
echo =========================================
pause
