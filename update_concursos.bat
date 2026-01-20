@echo off
REM =====================================================
REM BAT - Atualização de Concursos
REM Projeto: IA_TREVO4FOLHAS
REM =====================================================

REM Garante que o BAT rode na pasta raiz do projeto
cd /d "%~dp0"

REM Ativa UTF-8 (evita problemas com acentos)
chcp 65001 > nul

REM Mostra info
echo =========================================
echo 🚀 Iniciando atualização de concursos
echo =========================================

REM Executa o script Python
python START\update_concursos.py

REM Verifica erro
if errorlevel 1 (
    echo.
    echo ❌ ERRO ao executar update_concursos.py
) else (
    echo.
    echo ✅ Atualização concluída com sucesso
)

echo.
pause
