#!/bin/sh
# Production entrypoint: apply migrations, then start the API server.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] Applying database migrations (alembic upgrade head)..."
    alembic upgrade head
    echo "[entrypoint] Migrations applied."
else
    echo "[entrypoint] RUN_MIGRATIONS=false — skipping migrations."
fi

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --access-log \
    --log-level info
