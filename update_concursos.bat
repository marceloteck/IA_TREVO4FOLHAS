@echo off
cls

echo =========================================
echo   ATUALIZACAO DE CONCURSOS - IA LOTOFACIL
echo =========================================
echo.

REM ================================
REM ATIVAR AMBIENTE VIRTUAL
REM ================================
IF NOT EXIST venv\Scripts\activate.bat (
    echo ❌ Ambiente virtual nao encontrado.
    echo 👉 Execute install.bat primeiro.
    pause
    exit /b 1
)

call venv\Scripts\activate

echo ✅ Ambiente virtual ativado.
echo.

REM ================================
REM ATUALIZAR CONCURSOS
REM ================================
echo 🔄 Atualizando concursos no banco...
python START\update_concursos.py

IF ERRORLEVEL 1 (
    echo ❌ Erro durante a atualizacao dos concursos.
    pause
    exit /b 1
)

echo.
echo =========================================
echo ✅ ATUALIZACAO CONCLUIDA COM SUCESSO
echo =========================================
pause
