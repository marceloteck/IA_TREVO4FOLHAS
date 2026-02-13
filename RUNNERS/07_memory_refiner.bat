@echo off
setlocal
set ROOT=%~dp0..
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
call "%ROOT%\venv\Scripts\activate.bat"
python -c "from data.BD.connection import get_conn; from training.memory.memory_refiner import MemoryRefiner; import json, pathlib; cfg=json.loads(pathlib.Path('config/memory_refiner.json').read_text(encoding='utf-8')); c=get_conn(); print(MemoryRefiner(c,cfg).run_batch(cfg.get('batch_size',2000))); c.close()" >> "%ROOT%\logs\runner_memory_refiner_%TS%.log" 2>&1
endlocal
