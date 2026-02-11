@echo off
setlocal enabledelayedexpansion

echo =========================================
echo   GERAR CATALOGO POR CEREBRO - IA TREVO
echo =========================================

REM Ir para a pasta do projeto (onde está este .bat)
cd /d "%~dp0"

REM Ativar venv (se existir)
if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.

REM Config padrao (edite se quiser)
set SIZE=15
set JANELA=300
set PER_BRAIN=80
set TOP_BRAINS=12
set PERFIL=balanceado

echo [INFO] size       : %SIZE%
echo [INFO] janela     : %JANELA%
echo [INFO] per_brain  : %PER_BRAIN%
echo [INFO] top_brains : %TOP_BRAINS%
echo [INFO] perfil     : %PERFIL%
echo.

echo [RUN] Gerando catalogo por cerebro (top por 14/15)...
python "START\gerar_proximo_concurso.py" --por-cerebro --size %SIZE% --janela %JANELA% --per-brain %PER_BRAIN% --top-brains %TOP_BRAINS% --perfil %PERFIL%

if errorlevel 1 (
  echo.
  echo =========================================
  echo [ERRO] Falhou ao gerar o catalogo por cerebro.
  echo Dica: rode antes START\startBD.py e depois tente novamente.
  echo =========================================
  pause
  exit /b 1
)

echo.
echo =========================================
echo [OK] Catalogo por cerebro concluido!
echo Veja os relatorios em: reports\
echo =========================================

pause
endlocal

