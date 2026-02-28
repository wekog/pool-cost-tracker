# Portainer Environment Variablen

Dieses Projekt verwendet keine `.env` Datei mehr. Alle Variablen werden im Portainer Stack unter `Environment` gesetzt.

## Pflicht

- `PAPERLESS_BASE_URL`
- `PAPERLESS_TOKEN`

## Optional (mit App-Defaults)

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

## Beispiele

- Projekt A:
- `PROJECT_NAME=Pool`
- `PROJECT_TAG_NAME=Pool`
- `DEFAULT_CURRENCY=EUR`

- Projekt B:
- `PROJECT_NAME=Gartenhaus`
- `PROJECT_TAG_NAME=Gartenhaus`
- `DEFAULT_CURRENCY=EUR`
- `PROJECT_CATEGORY_PRESETS=Material,Reparatur,Wartung`

## UI

Die React-UI benötigt keine eigenen Environment-Variablen. Sie läuft unter Port 8501 und nutzt intern den Nginx-Proxy auf `/api`, der Requests an `http://api:8000` weiterleitet.
