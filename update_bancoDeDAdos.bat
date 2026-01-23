@echo off
REM =====================================================
REM BAT - Atualização de banco de dados
REM Projeto: IA_TREVO4FOLHAS
REM =====================================================

REM Garante que o BAT rode na pasta raiz do projeto
cd /d "%~dp0"

REM Ativa UTF-8 (evita problemas com acentos)
chcp 65001 > nul

REM Mostra info
echo =========================================
echo 🚀 Iniciando atualização de banco de dados
echo =========================================

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
