@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "CFG=%~dp0..\config\governance.json"

if not exist "%CFG%" (
  echo [ERRO] Arquivo nao encontrado: %CFG%
  echo Crie o arquivo config\governance.json antes de usar este toggle.
  pause
  goto :eof
)

:show
echo ====================================
echo TOGGLE GOVERNANCE
echo Arquivo: %CFG%
for /f "delims=" %%A in ('powershell -NoProfile -Command "try { $j=Get-Content -Raw '%CFG%' ^| ConvertFrom-Json; if($j.enabled){'ON'} else {'OFF'} } catch { 'UNKNOWN' }"') do set "STATE=%%A"
echo Estado atual: %STATE%
echo ------------------------------------
echo 1 - Ligar Governance
echo 2 - Desligar Governance
echo 0 - Sair
set /p OP=Escolha: 

if "%OP%"=="1" goto on
if "%OP%"=="2" goto off
if "%OP%"=="0" goto :eof

echo Opcao invalida.
goto show

:on
powershell -NoProfile -Command "try { $p='%CFG%'; $j=Get-Content -Raw $p | ConvertFrom-Json; $j.enabled=$true; $j | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $p; exit 0 } catch { exit 1 }"
if errorlevel 1 goto ps_fail
echo [OK] Governance LIGADA.
goto show

:off
powershell -NoProfile -Command "try { $p='%CFG%'; $j=Get-Content -Raw $p | ConvertFrom-Json; $j.enabled=$false; $j | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $p; exit 0 } catch { exit 1 }"
if errorlevel 1 goto ps_fail
echo [OK] Governance DESLIGADA.
goto show

:ps_fail
echo [AVISO] Falha ao alterar JSON via PowerShell.
echo Edite manualmente: config\governance.json ^> "enabled": true/false
pause
goto :eof
