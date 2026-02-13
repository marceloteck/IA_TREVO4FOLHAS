@echo off
setlocal
:menu
cls
echo ====================================
echo IA_TREVO4FOLHAS - RUNNERS MENU
echo ====================================
echo 1 - Status do aprendizado
echo 2 - Update concursos
echo 3 - Backtest smart continuo
echo 4 - Gerar jogos (producao)
echo 5 - Gerar jogos (pesquisa)
echo 6 - Conferir acertos pendentes
echo 7 - Rodar Memory Refiner
echo 8 - Gerar relatorio CLI + HTML
echo 9 - AUTO pos-concurso (update + check + treino)
echo 0 - Sair
set /p OP=Escolha: 
if "%OP%"=="1" call "%~dp001_status_aprendizado.bat"
if "%OP%"=="2" call "%~dp002_update_concursos.bat"
if "%OP%"=="3" call "%~dp003_backtest_smart_continuo.bat"
if "%OP%"=="4" call "%~dp004_generate_producao.bat"
if "%OP%"=="5" call "%~dp005_generate_pesquisa.bat"
if "%OP%"=="6" call "%~dp006_check_acertos.bat"
if "%OP%"=="7" call "%~dp007_memory_refiner.bat"
if "%OP%"=="8" call "%~dp008_report.bat"
if "%OP%"=="9" call "%~dp009_auto_pos_concurso.bat"
if "%OP%"=="0" goto end
pause
goto menu
:end
endlocal
