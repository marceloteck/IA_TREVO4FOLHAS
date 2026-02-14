@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
chcp 65001 >nul
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

echo [RUN] Rodando Memory Refiner
python -c "from data.BD.connection import get_conn; from training.memory.memory_refiner import MemoryRefiner; import json, pathlib; cfg=json.loads(pathlib.Path('config/memory_refiner.json').read_text(encoding='utf-8')); c=get_conn(); print(MemoryRefiner(c,cfg).run_batch(cfg.get('batch_size',2000))); c.close()"
if errorlevel 1 (
  echo [ERRO] Falha ao rodar Memory Refiner.
  pause
  exit /b 1
)

pause
endlocal
