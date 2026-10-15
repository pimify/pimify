#!/bin/sh
# Pimify container entrypoint (no uv at runtime — deps are baked into
# /app/.venv at build time; PATH in the Dockerfile points there).
# Gunicorn is the last process. NOTE: gunicorn (not runserver) is
# intentional here — a container is a deployment artifact, not a dev loop.
# MODE comes from the container environment (-e MODE=... / --env-file),
# defaulting to development; prod containers pass MODE=production.
set -e

echo "Ensuring necessary directories exist..."
mkdir -p data backups media feeds static

echo "Running migrations..."
# --fake-initial: see install.sh — upgrades pre-uv installs whose api tables
# exist without a recorded migration; fresh DBs migrate normally.
python manage.py migrate --fake-initial

echo "Collecting static files..."
python manage.py collectstatic --noinput

# NOTE: `manage.py scheduler` never returns (waits in the foreground until
# SIGTERM/SIGINT) — run it as a separate replica/service in production,
# not in this entrypoint. See script/deploy/ for supervisor templates.

echo "Starting the server..."
exec gunicorn core.wsgi:application -c /etc/gunicorn/gunicorn.conf.py
