@echo off
setlocal
cd /d "%~dp0"

echo ========================================================
echo               Starting FoodWise AI
echo ========================================================

REM 1. Set up virtual environment if missing
if not exist "backend\.venv" (
    echo [*] Creating virtual environment in backend\.venv...
    python -m venv backend\.venv
)

REM 2. Set up backend .env if missing
if not exist "backend\.env" (
    echo [*] Creating backend\.env from .env.example...
    copy .env.example backend\.env >nul
)

REM 3. Install dependencies
echo [*] Checking dependencies...
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt --quiet

REM 4. Seed database if not yet created
if not exist "backend\foodwise.db" (
    echo [*] Initializing and seeding database...
    cd backend
    .venv\Scripts\python seed.py
    cd ..
)

echo [*] Starting server at http://localhost:8000 ...
echo [*] Press Ctrl+C to stop.
echo ========================================================

REM Launch browser in 2 seconds
start "" cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

REM Run FastAPI server with Uvicorn
cd backend
.venv\Scripts\uvicorn main:app --reload --host 0.0.0.0 --port 8000
