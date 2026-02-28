# pool-cost-tracker

Lokale WebApp (FastAPI + React/Vite) zur Auswertung projektbezogener Kosten aus Paperless-ngx plus manuellen Kostenpositionen. Projektname, Tag und Defaults sind per Environment konfigurierbar.

## Features

- Sync von Paperless-ngx per REST API (`POST /sync`)
- Filter auf konfigurierbares Projekt-Tag (`PROJECT_TAG_NAME`, Default `Pool`)
- Projektkontext per ENV (`PROJECT_NAME`, `PROJECT_TAG_NAME`, `DEFAULT_CURRENCY`, `PROJECT_TIMEZONE`)
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

## Architecture

- FastAPI API
- React SPA
- Nginx als statischer Webserver fuer die gebaute React-App mit `/api` Proxy auf FastAPI

## Deployment mit Portainer

Dieses Projekt verwendet **keine `.env` Datei** mehr.
Alle Variablen werden im Portainer Stack unter `Environment` gesetzt.

Pflicht-Variablen (API startet sonst nicht):

- `PAPERLESS_BASE_URL`
- `PAPERLESS_TOKEN`

Projekt-Variablen:

- `PROJECT_NAME`
- `PROJECT_TAG_NAME`

Optionale Variablen (mit App-Defaults):

- `PROJECT_NAME` (Default: `Pool`)
- `PROJECT_TAG_NAME` (Default: `Pool`)
- `POOL_TAG_NAME` (Legacy-Fallback, nur wenn `PROJECT_TAG_NAME` nicht gesetzt ist)
- `DEFAULT_CURRENCY` (Default: `EUR`)
- `PROJECT_TIMEZONE` (Default: `Europe/Berlin`)
- `PROJECT_CATEGORY_PRESETS` (comma-separated, Default: leer)
- `SYNC_PAGE_SIZE` (Default: `100`)
- `SYNC_LOOKBACK_DAYS` (Default: `365`)
- `DATABASE_URL` (Default: `sqlite:////data/app.db`)
- `SCHEDULER_ENABLED` (Default: `false`)
- `SCHEDULER_INTERVAL_MINUTES` (Default: `360`)
- `SCHEDULER_RUN_ON_STARTUP` (Default: `true`)

Empfehlung: pro Projekt einen separaten Stack mit eigenem Datenpfad oder eigener Volume-Zuordnung nutzen, damit jedes Projekt eine getrennte SQLite-DB hat.

Beispiele:

- Projekt A:
- `PROJECT_NAME=Pool`
- `PROJECT_TAG_NAME=Pool`
- `DEFAULT_CURRENCY=EUR`

- Projekt B:
- `PROJECT_NAME=Gartenhaus`
- `PROJECT_TAG_NAME=Gartenhaus`
- `DEFAULT_CURRENCY=EUR`
- `PROJECT_CATEGORY_PRESETS=Material,Reparatur,Wartung`

UI:

- Keine zusätzlichen UI-ENV nötig. Die React-App spricht relativ über `/api` und wird im gleichen Container-Proxy auf `http://api:8000` weitergeleitet.

Details: Siehe `docs/portainer-env.md`

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
- `PATCH /manual-costs/{id}/archive`
- `PATCH /manual-costs/{id}/restore`
- `GET /summary`
- `GET /export.csv`
- `GET /config`

## Frontend

- Die produktive UI liegt im Ordner `web`
- `web/nginx/default.conf` servt die SPA und proxyt `/api/*` intern auf `api:8000`
- Docker Compose startet nur noch den React+Nginx-Container als `ui`

## Tests

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-api.txt -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

## Paperless API Nutzung

1. `GET ${PAPERLESS_BASE_URL}/api/tags/` (paginierend), exakter Match `name == PROJECT_TAG_NAME`
2. `GET ${PAPERLESS_BASE_URL}/api/documents/?tags__id=<project_tag_id>&page_size=<SYNC_PAGE_SIZE>&ordering=-created&truncate_content=false`

Wenn der Tag fehlt, bricht der Sync mit klarer Fehlermeldung ab.
