# CausalStream Backend

FastAPI service that owns sessions, caption history, the public REST API and the WebSocket gateway to the AI service. This directory is an independent repository.

## Run locally

Requirements: Python 3.11+ and a running AI service for LIVE mode. From this directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Set `AI_SERVICE_URL`, `DATABASE_URL` and `CORS_ALLOWED_ORIGINS` in `.env` for the deployment. `AI_SERVICE_URL` should be an internal address reachable only by the Backend. The frontend uses the Backend origin as `VITE_API_BASE_URL`. DEMO sessions can run without a real model; LIVE sessions require an available AI service.

API documentation: `http://127.0.0.1:8000/docs`. Health endpoints: `/healthz` and `/readyz`.

## Verify

```bash
python -m pytest -q
python -m ruff check app tests
```

The integration test requiring already running services is skipped unless `RUN_E2E_SERVICES=1`. Alembic migrations are included. Local databases, virtual environments, caches and `.env` are excluded from Git and Docker build context.
