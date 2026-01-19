@echo off
echo =========================================
echo   TREINO INCREMENTAL - IA LOTOFACIL
echo =========================================

call venv\Scripts\activate

python START\train_incremental.py

echo =========================================
echo   FIM DO TREINO
echo =========================================
pause
