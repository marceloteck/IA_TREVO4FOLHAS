@echo off
setlocal EnableExtensions
set "ROOT=%~dp0.."
cd /d "%ROOT%"
call "RUNNERS\02_update_concursos.bat"
call "RUNNERS\06_check_acertos.bat"
call "RUNNERS\03_backtest_smart_continuo.bat"
endlocal
