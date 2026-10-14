#!/bin/sh
# Migrations and seed are idempotent: a restart keeps the existing data and bookings.
set -e
alembic upgrade head
python -m app.seed
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log  # access log: app middleware
