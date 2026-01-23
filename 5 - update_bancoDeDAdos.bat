@echo off
echo =====================================================
echo Atualização de banco de dados
echo Projeto: IA_TREVO4FOLHAS
echo =====================================================
echo.

REM Garante que o BAT rode na pasta raiz do projeto
cd /d "%~dp0"

REM Ativar venv (se existir)
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.


REM Ativa UTF-8 (evita problemas com acentos)
chcp 65001 > nul

REM Mostra info
echo =========================================
echo 🚀 Iniciando atualização de banco de dados
echo =========================================
echo.

REM Executa o script Python
python scripts\merge_temp_dbs.py

REM Verifica erro
if errorlevel 1 (
    echo.
    echo ❌ ERRO ao executar merge_temp_dbs.py
) else (
    echo.
    echo ✅ Atualização concluída com sucesso
)

echo.
pause
