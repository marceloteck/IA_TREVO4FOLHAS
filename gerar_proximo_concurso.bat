@echo off
echo =========================================
echo   GERAR JOGOS - PROXIMO CONCURSO (BRAINHUB)
echo =========================================

call venv\Scripts\activate

REM 10 jogos de 15 dezenas (padrão)
python START\gerar_proximo_concurso.py --size 15 --qtd 10

echo.
echo =========================================
echo   RELATORIO SALVO EM /reports
echo =========================================
pause
