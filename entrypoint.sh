#!/bin/sh
# Container startup: apply DB migrations, then launch the API.
# Render injects $PORT; fall back to 8000 for local runs.
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting SRH Backend API on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
