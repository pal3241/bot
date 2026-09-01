@echo off
setlocal
set "BOT_DIR=%~dp0"
set "BOT_PYTHON=%BOT_DIR%.venv\Scripts\python.exe"

if not exist "%BOT_PYTHON%" (
    echo Environment proyek tidak ditemukan.
    echo Jalankan: python -m venv .venv
    echo Lalu: .venv\Scripts\python.exe -m pip install -r requirements.txt
    exit /b 1
)

cd /d "%BOT_DIR%"
"%BOT_PYTHON%" main.py
exit /b %errorlevel%
