# Portainer Environment Variablen

Dieses Projekt verwendet keine `.env` Datei mehr. Alle Variablen werden im Portainer Stack unter `Environment` gesetzt.

## Pflicht

- `PAPERLESS_BASE_URL`
- `PAPERLESS_TOKEN`

## Optional (mit App-Defaults)

- `POOL_TAG_NAME` (Default: `Pool`)
- `SYNC_PAGE_SIZE` (Default: `100`)
- `SYNC_LOOKBACK_DAYS` (Default: `365`)
- `DATABASE_URL` (Default: `sqlite:////data/app.db`)
- `SCHEDULER_ENABLED` (Default: `false`)
- `SCHEDULER_INTERVAL_MINUTES` (Default: `360`)
- `SCHEDULER_RUN_ON_STARTUP` (Default: `true`)

## UI

Die React-UI benötigt keine eigenen Environment-Variablen. Sie läuft unter Port 8501 und nutzt intern den Nginx-Proxy auf `/api`, der Requests an `http://api:8000` weiterleitet.
