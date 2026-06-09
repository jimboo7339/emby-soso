#!/usr/bin/env bash
set -euo pipefail

cd /app/backend

echo "[entrypoint] Running database migrations..."
alembic upgrade head

MODE="standalone"
if [[ "${REDIS_ENABLED:-auto}" == "true" ]] || { [[ "${REDIS_ENABLED:-auto}" == "auto" ]] && [[ -n "${REDIS_URL:-}" ]]; }; then
  MODE="redis-enhanced"
fi

echo "[entrypoint] Starting emby-soso (mode: ${MODE}) on port ${APP_PORT:-8080}"

exec gunicorn app.main:app \
  --workers "${WEB_WORKERS:-2}" \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${APP_PORT:-8080}" \
  --access-logfile - \
  --error-logfile -
