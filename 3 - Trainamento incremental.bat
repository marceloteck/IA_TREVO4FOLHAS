@echo off
echo =========================================
echo Trainamento Incremental
echo Projeto: IA_TREVO4FOLHAS
echo =========================================
echo.
echo.

REM Ativar venv (se existir)
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
    call venv\Scripts\activate
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
echo.

python -m training.trainer_v2
python -m training.backtest.backtest_engine --hours 24 --block-size 250 --min-mem 14 --aggressive
pause
