# pool-cost-tracker

Lokale WebApp (FastAPI + React/Vite) zur Auswertung von Pool-Kosten aus Paperless-ngx (Tag-Filter `Pool`) plus manuellen Kostenpositionen.

## Features

- Sync von Paperless-ngx per REST API (`POST /sync`)
- Filter nur auf Tag `POOL_TAG_NAME` (Default `Pool`)
- OCR-Extraktion von Unternehmen + Brutto/Endbetrag (EUR)
- Speicherung in SQLite (`invoices`, `manual_costs`)
- Manuelle Kostenpositionen
- Dashboard mit KPIs, Unternehmen, Kategorien
- CSV-Export
- Optionaler Scheduler
- Alembic Migrationen

## Tech-Stack

- Backend: Python 3.12, FastAPI, httpx, SQLAlchemy, Alembic
- UI: React 18, Vite, TypeScript, Nginx (`/api` Reverse Proxy auf FastAPI)
- DB: SQLite (`/data`)
- Tests: pytest

## Deployment mit Portainer

Dieses Projekt verwendet **keine `.env` Datei** mehr.
Alle Variablen werden im Portainer Stack unter `Environment` gesetzt.

Pflicht-Variablen (API startet sonst nicht):

- `PAPERLESS_BASE_URL`
- `PAPERLESS_TOKEN`

Optionale Variablen (mit App-Defaults):

- `POOL_TAG_NAME` (Default: `Pool`)
- `SYNC_PAGE_SIZE` (Default: `100`)
- `SYNC_LOOKBACK_DAYS` (Default: `365`)
- `DATABASE_URL` (Default: `sqlite:////data/app.db`)
- `SCHEDULER_ENABLED` (Default: `false`)
- `SCHEDULER_INTERVAL_MINUTES` (Default: `360`)
- `SCHEDULER_RUN_ON_STARTUP` (Default: `true`)

UI:

- Keine zusätzlichen UI-ENV nötig. Die React-App spricht relativ über `/api` und wird im gleichen Container-Proxy auf `http://api:8000` weitergeleitet.

Details: `/Users/weko/Documents/Codex/Pool_Kosten/docs/portainer-env.md`

## Start mit Docker Compose

```bash
docker compose up --build
```

## Aufruf

- UI: `http://<host>:8501`
- API (externes Mapping): `http://<host>:18000/docs`

## Scheduler

- `SCHEDULER_ENABLED=false`: kein Background-Job
- `SCHEDULER_ENABLED=true`: optional Run on Startup + Intervall-Sync

## Alembic Migrationen

```bash
docker compose exec api alembic upgrade head
```

## API Endpoints

- `POST /sync`
- `GET /invoices`
- `PUT /invoices/{id}`
- `POST /manual-costs`
- `GET /manual-costs`
- `PUT /manual-costs/{id}`
- `DELETE /manual-costs/{id}`
- `GET /summary`
- `GET /export.csv`
- `GET /config`

## Frontend

- Die produktive UI liegt unter `/Users/weko/Documents/Codex/Pool_Kosten/web`
- `web/nginx/default.conf` servt die SPA und proxyt `/api/*` intern auf `api:8000`
- Der alte Streamlit-Ordner `/Users/weko/Documents/Codex/Pool_Kosten/ui` bleibt nur als Legacy-Referenz erhalten und wird von Docker Compose nicht mehr verwendet

## Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

## Paperless API Nutzung

1. `GET ${PAPERLESS_BASE_URL}/api/tags/` (paginierend), exakter Match `name == POOL_TAG_NAME`
2. `GET ${PAPERLESS_BASE_URL}/api/documents/?tags__id=<pool_tag_id>&page_size=<SYNC_PAGE_SIZE>&ordering=-created&truncate_content=false`

Wenn der Tag fehlt, bricht der Sync mit klarer Fehlermeldung ab.
