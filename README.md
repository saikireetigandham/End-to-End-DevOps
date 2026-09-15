# Juniper & Stone

A small Flask ordering app for Juniper & Stone, a neighborhood restaurant. Guests can browse the menu, build a session-backed cart, and submit an order that is persisted in SQLite.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = "src"
python src/app.py
```

Open `http://127.0.0.1:5000`. The database is created and seeded at `src/instance/restaurant.sqlite3` on first run.

## Test

```powershell
pytest -q
```

## Docker

```powershell
docker build -t juniper-stone .
docker run --rm -p 5000:5000 juniper-stone
```