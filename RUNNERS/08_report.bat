@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Gerando relatorio CLI
python -m training.reporting.report_cli --last-run
if errorlevel 1 (
  echo [ERRO] Falha ao gerar report_cli.
  pause
  exit /b 1
)

for /f %%r in ('python -c "from data.BD.connection import get_conn; c=get_conn(); row=c.execute('SELECT id FROM runs ORDER BY id DESC LIMIT 1').fetchone(); print(row[0] if row else ''); c.close()"') do set RID=%%r
if not "%RID%"=="" (
  echo [RUN] Gerando relatorio HTML do run %RID%
  python -m training.reporting.report_html --run-id %RID%
)

pause
endlocal
