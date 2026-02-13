@echo off
setlocal
set ROOT=%~dp0..
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
call "%ROOT%\venv\Scripts\activate.bat"
python "%ROOT%\training\backtest\backtest_smart_engine.py" --steps 0 --minutes 0 >> "%ROOT%\logs\runner_backtest_smart_%TS%.log" 2>&1
endlocal
