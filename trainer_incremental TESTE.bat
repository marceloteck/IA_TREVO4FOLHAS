@echo off
call venv\Scripts\activate
python -m training.backtest.backtest_engine --hours 0.04 --block-size 25 --min-mem 13 --aggressive
pause
