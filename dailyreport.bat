@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"

rem First run: create virtual environment
if not exist "%PY%" (
    echo [dailyreport] First run, creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [dailyreport] Failed to create virtual environment. Please install Python 3.10+.
        pause
        exit /b 1
    )
)

rem First run: install dependencies
if not exist ".venv\.deps_installed" (
    echo [dailyreport] Installing dependencies...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [dailyreport] Failed to install dependencies.
        pause
        exit /b 1
    )
    type nul > ".venv\.deps_installed"
)

rem First run: remind to configure .env
if not exist ".env" (
    echo [dailyreport] .env not found. Copy .env.example to .env and fill in your API key.
)

"%PY%" main.py
if errorlevel 1 pause
endlocal
