#!/bin/sh
# Pimify container entrypoint (uv, OCI). Gunicorn is the last process.
set -e

echo "Syncing dependencies with uv..."
uv sync --locked --no-dev

echo "Ensuring necessary directories exist..."
mkdir -p data backups media

echo "Running migrations..."
# --fake-initial: see install.sh — upgrades pre-uv installs whose api tables
# exist without a recorded migration; fresh DBs migrate normally.
uv run python manage.py migrate --fake-initial

echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

# NOTE: `manage.py scheduler` is a blocking BackgroundScheduler — run it as a
# separate replica/service in production, not in this entrypoint.

echo "Starting the server..."
exec uv run gunicorn core.wsgi:application -c /etc/gunicorn/gunicorn.conf.py
