# FoodWise AI — surplus identification and redistribution

FastAPI + SQLAlchemy (PostgreSQL or SQLite) backend with a React frontend served by the same app.

## Quick Start (One Command)
- **Windows (CMD / double-click)**: Run [`run.bat`](file:///c:/Users/HP/OneDrive/Desktop/foodwise-ai/run.bat)
- **Windows (PowerShell)**: Run [`.\run.ps1`](file:///c:/Users/HP/OneDrive/Desktop/foodwise-ai/run.ps1)

This automatically configures the environment, installs packages, seeds demo accounts, opens `http://localhost:8000`, and starts the server.

## Manual Run
```bash
cd backend && python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env        # set SECRET_KEY, ADMIN_PASSWORD; use DATABASE_URL for PostgreSQL
python seed.py                 # admin + clearly named "Demo …" records (optional)
uvicorn main:app --reload --host 0.0.0.0 --port 8000  # app: http://localhost:8000  API docs: /docs
pytest tests                   # allocation, expiry, and role checks
```
Demo logins after seeding: `store@demo.local`, `hope@demo.local` (password `Demo@1234`), admin `admin@foodwise.local` (your `ADMIN_PASSWORD`).

## What is implemented
Supermarket and NGO registration/login (bcrypt, JWT, role checks) · inventory CRUD, barcode/SKU lookup, sales recording · live expiry alerts · waste-risk score and reorder hint · surplus listings with server-side expiry and over-allocation guards · NGO matching score with reasons · request, accept/reject, pickup scheduling and confirmation · notifications · impact dashboard · admin overview.

## Not implemented (be explicit in your report)
- **Prophet/LSTM forecasting and the separate FastAPI prediction microservice.** Risk uses a 14-day moving average of recorded sales (`services.forecast`); with no sales it is labelled low confidence.
- CSV bulk upload, POS REST integration, camera barcode scanning (manual barcode lookup works).
- Map display, calendar UI, image upload, email/SMS (notifications are in-app only), Alembic migrations (tables are created on startup).
- Impact factors (1 unit ≈ 0.5 kg, 0.5 kg per meal, 2.5 kg CO₂e per kg) are assumptions set in `.env`.
- The frontend loads React and Babel from cdnjs; move it to Vite for production.
