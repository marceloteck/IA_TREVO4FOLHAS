@echo off
call venv\Scripts\activate
python -m training.backtest.backtest_engine --hours 24 --block-size 250 --min-mem 14 --aggressive
pause
