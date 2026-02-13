@echo off
setlocal
set ROOT=%~dp0..
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
call "%ROOT%\venv\Scripts\activate.bat"
python "%ROOT%\training\user\check_hits_pending.py" --auto >> "%ROOT%\logs\runner_check_hits_%TS%.log" 2>&1
endlocal
