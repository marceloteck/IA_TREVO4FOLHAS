@echo off
echo =========================================
echo   INSTALADOR - IA LOTOFACIL (WINDOWS)
echo =========================================

python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo ❌ Python nao encontrado.
    echo 👉 Instale Python 3.10+ e marque "Add to PATH"
    pause
    exit /b
)

echo ✅ Python encontrado.

IF NOT EXIST venv (
    echo 📦 Criando ambiente virtual...
    python -m venv venv
)

call venv\Scripts\activate

echo 🔄 Atualizando pip...
python -m pip install --upgrade pip

echo 📥 Instalando dependencias...
pip install -r requirements.txt

echo 🗄️ Preparando banco (schema + import CSV)...
python START\startBD.py

echo =========================================
echo ✅ INSTALACAO CONCLUIDA COM SUCESSO
echo =========================================
pause
