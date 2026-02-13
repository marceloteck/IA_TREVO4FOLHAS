@echo off
setlocal
set ROOT=%~dp0..
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
call "%ROOT%\venv\Scripts\activate.bat"
python "%ROOT%\training\user\generate_for_user.py" --mode research >> "%ROOT%\logs\runner_generate_research_%TS%.log" 2>&1
endlocal
