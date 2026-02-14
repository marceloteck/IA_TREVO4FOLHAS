@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul

echo =========================================
echo   STATUS DO APRENDIZADO (BANCO / CEREBROS)
echo =========================================

echo.
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
python START\status_aprendizado.py
if errorlevel 1 (
  echo [ERRO] Falha ao consultar status.
  pause
  exit /b 1
)

echo.
echo =========================================
echo   FINALIZADO
echo =========================================
pause
endlocal
