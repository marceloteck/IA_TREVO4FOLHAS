@echo off
setlocal enabledelayedexpansion

echo =====================================================
echo   BACKTEST SUPER INTELIGENTE AUTONOMO - IA TREVO
echo =====================================================

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
  echo [OK] Ativando venv...
  call "venv\Scripts\activate.bat"
) else (
  echo [AVISO] venv nao encontrado. Rodando com Python do sistema...
)

echo.
REM --------- PARAMETROS PADRAO (PODE EDITAR) ----------
set STEPS=240
set MINUTES=0
set RECENT_WINDOW=260
set AVALIAR_TOP_K=50
set UCB_C=1.25
set RECIPE_UCB_C=1.10
set RECIPE_EVOLVE_EVERY=12
set RECIPE_MAX_MEMBERS=24
set RECIPE_PROMOTE_REWARD=2.8
set RECIPE_MIN_PULLS=8
set REVIVE_PARKED_EVERY=30
set REWARD_Q15=5.0
set REWARD_Q14=1.5
set MIN_MEM=12
set RUN_NAME=smart_autonomo_v1
set SEED=


echo [INFO] steps                 : %STEPS%
echo [INFO] minutes               : %MINUTES%
echo [INFO] recent_window         : %RECENT_WINDOW%
echo [INFO] avaliar_top_k         : %AVALIAR_TOP_K%
echo [INFO] ucb_c (arms)          : %UCB_C%
echo [INFO] recipe_ucb_c          : %RECIPE_UCB_C%
echo [INFO] recipe_evolve_every   : %RECIPE_EVOLVE_EVERY%
echo [INFO] recipe_max_members    : %RECIPE_MAX_MEMBERS%
echo [INFO] recipe_promote_reward : %RECIPE_PROMOTE_REWARD%
echo [INFO] recipe_min_pulls      : %RECIPE_MIN_PULLS%
echo [INFO] revive_parked_every   : %REVIVE_PARKED_EVERY%
echo [INFO] reward_q15            : %REWARD_Q15%
echo [INFO] reward_q14            : %REWARD_Q14%
echo [INFO] min_mem               : %MIN_MEM%
echo [INFO] run_name              : %RUN_NAME%
echo.

echo [RUN] Iniciando backtest super inteligente (foco 14/15)...
set CMD=python -m training.backtest.backtest_smart_engine --steps %STEPS% --minutes %MINUTES% --recent-window %RECENT_WINDOW% --avaliar-top-k %AVALIAR_TOP_K% --ucb-c %UCB_C% --recipe-ucb-c %RECIPE_UCB_C% --recipe-evolve-every %RECIPE_EVOLVE_EVERY% --recipe-max-members %RECIPE_MAX_MEMBERS% --recipe-promote-reward %RECIPE_PROMOTE_REWARD% --recipe-min-pulls %RECIPE_MIN_PULLS% --revive-parked-every %REVIVE_PARKED_EVERY% --reward-q15 %REWARD_Q15% --reward-q14 %REWARD_Q14% --min-mem %MIN_MEM% --run-name %RUN_NAME%

if not "%SEED%"=="" (
  set CMD=!CMD! --seed %SEED%
)

echo [CMD] !CMD!
!CMD!

if errorlevel 1 (
  echo.
  echo =====================================================
  echo [ERRO] Falha ao executar o backtest super inteligente.
  echo Dicas:
  echo  - Rode START\startBD.py para garantir o banco
  echo  - Rode START\update_concursos.py para atualizar concursos
  echo =====================================================
  pause
  exit /b 1
)

echo.
echo =====================================================
echo [OK] Backtest super inteligente concluido!
echo Acompanhe no banco:
echo  - backtest_smart_runs
echo  - backtest_smart_steps
echo  - backtest_smart_recipes
echo  - backtest_smart_recipe_trials
echo =====================================================

pause
endlocal
