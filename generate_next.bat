@echo off
echo =========================================
echo   GERAR JOGOS - PROXIMO CONCURSO
echo =========================================

call venv\Scripts\activate

python START\generate_next.py

echo =========================================
echo   FIM
echo =========================================
pause
