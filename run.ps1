Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "              Starting FoodWise AI                      " -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Virtual environment
if (-not (Test-Path "backend\.venv")) {
    Write-Host "[*] Creating virtual environment in backend\.venv..." -ForegroundColor Yellow
    python -m venv backend\.venv
}

# 2. .env configuration
if (-not (Test-Path "backend\.env")) {
    Write-Host "[*] Copying .env.example to backend\.env..." -ForegroundColor Yellow
    Copy-Item ".env.example" "backend\.env"
}

# 3. Dependencies
Write-Host "[*] Checking / installing dependencies..." -ForegroundColor Yellow
& "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" --quiet

# 4. Seed database
if (-not (Test-Path "backend\foodwise.db")) {
    Write-Host "[*] Initializing and seeding database..." -ForegroundColor Yellow
    Push-Location backend
    & ".\.venv\Scripts\python.exe" seed.py
    Pop-Location
}

Write-Host "[*] Launching browser at http://localhost:8000..." -ForegroundColor Green
Start-Process "http://localhost:8000"

Write-Host "[*] Server running on http://localhost:8000 (Ctrl+C to exit)..." -ForegroundColor Cyan
Push-Location backend
& ".\.venv\Scripts\uvicorn.exe" main:app --reload --host 0.0.0.0 --port 8000
Pop-Location
