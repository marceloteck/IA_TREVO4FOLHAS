@echo off
setlocal
set ROOT=%~dp0..
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
call "%ROOT%\venv\Scripts\activate.bat"
python "%ROOT%\training\reporting\report_cli.py" --last-run >> "%ROOT%\logs\runner_report_%TS%.log" 2>&1
for /f %%r in ('python -c "from data.BD.connection import get_conn; c=get_conn(); row=c.execute('SELECT id FROM runs ORDER BY id DESC LIMIT 1').fetchone(); print(row[0] if row else ''); c.close()"') do set RID=%%r
if not "%RID%"=="" python "%ROOT%\training\reporting\report_html.py" --run-id %RID% >> "%ROOT%\logs\runner_report_%TS%.log" 2>&1
endlocal
