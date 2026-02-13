@echo off
setlocal
set ROOT=%~dp0..
call "%ROOT%\RUNNERS\02_update_concursos.bat"
call "%ROOT%\RUNNERS\06_check_acertos.bat"
call "%ROOT%\RUNNERS\03_backtest_smart_continuo.bat"
endlocal
