@echo off
setlocal EnableExtensions
cd /d "%~dp0"

chcp 65001 >nul

title IA_TREVO4FOLHAS - APRENDIZADO CONTINUO

echo =====================================================
echo   INICIAR INTELIGENCIA ARTIFICIAL (APRENDIZADO CONTINUO)
echo =====================================================
echo Este e o BAT principal para deixar a IA rodando sempre.
echo.

if exist "venv\Scripts\activate.bat" (
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrada.
  echo [DICA] Execute "1 - Install.bat" antes de continuar.
)

:loop
echo.
echo [RUN] Iniciando ciclo continuo da IA em %date% %time%
python -u -m training.backtest.backtest_smart_engine --steps 0 --minutes 0 --progress-every 5 --summary-every 50 --save-every 10 --run-name inteligencia_artificial_continua
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo [OK] Processo encerrado normalmente (provavel parada manual).
  goto end
)

echo [AVISO] Processo caiu com codigo %RC%. Reiniciando em 10 segundos...
timeout /t 10 /nobreak >nul
goto loop

:end
echo.
echo [FIM] Execucao encerrada.
pause
endlocal
