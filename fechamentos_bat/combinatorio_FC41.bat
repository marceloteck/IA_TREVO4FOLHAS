@echo off
setlocal
pushd "%~dp0.."
python START\gerar_fechamento_auto.py --code FC41 %*
popd
