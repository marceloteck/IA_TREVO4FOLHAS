@echo off
setlocal enabledelayedexpansion

echo =========================================
echo   GERAR PROXIMO CONCURSO - IA TREVO
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
set PERFIL=agressivo
set JANELA=300
set PER_BRAIN=120
set TOP_N=250
set MAX_SIM=0.78

echo.
echo [INFO] Perfil   : %PERFIL%
echo [INFO] Janela   : %JANELA%
echo [INFO] per_brain: %PER_BRAIN%
echo [INFO] top_n    : %TOP_N%
echo [INFO] max_sim  : %MAX_SIM%
echo.

echo [RUN] Gerando jogos (15 e 18) e salvando no banco...
python "START\gerar_proximo_concurso.py" --size 15 --qtd 10 --second-size 18 --second-qtd 8 --perfil %PERFIL% --janela %JANELA% --per-brain %PER_BRAIN% --top-n %TOP_N% --max-sim %MAX_SIM% --salvar-db

if errorlevel 1 (
  echo.
  echo =========================================
  echo [ERRO] Falhou ao gerar os jogos.
  echo Dica: rode antes START\startBD.py e depois tente novamente.
  echo =========================================
  pause
  exit /b 1
)

echo.
echo =========================================
echo [OK] Geracao concluida com sucesso!
echo Veja os relatorios em: reports\
echo =========================================

pause
endlocal
