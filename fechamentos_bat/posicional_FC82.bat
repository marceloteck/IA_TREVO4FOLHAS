@echo off
setlocal
pushd "%~dp0.."
python START\gerar_fechamento_posicional_auto.py --code FC82 %*
popd
