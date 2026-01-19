@echo off
echo =========================================
echo   ATUALIZAR CONCURSOS (CSV -> SQLITE)
echo =========================================

call venv\Scripts\activate

python START\update_concursos.py

echo =========================================
echo   FIM
echo =========================================
pause
