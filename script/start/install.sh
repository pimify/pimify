#!/bin/bash
# Pimify dev setup (uv). Run from project root.
set -e

# Check for uv (install from https://docs.astral.sh/uv/ if missing)
if ! command -v uv &>/dev/null; then
    echo "uv is not installed. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Sync locked dependencies (creates .venv on first run)
echo "Syncing dependencies with uv..."
uv sync --locked

# Ensure .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Create data/backup/media dirs
echo "Creating data, backups and media directories..."
mkdir -p data backups media

# Migrations are committed (api/migrations/). Never generate them at runtime —
# fail loudly if models changed without a migration.
echo "Checking for missing migrations..."
uv run python manage.py makemigrations --check --dry-run

echo "Running migrations..."
# --fake-initial: pre-uv installs already have the api tables (old scripts
# generated migrations at runtime, so no migration was ever recorded).
# Django marks 0001_initial applied when its tables exist, runs it normally
# on fresh DBs. Safe for both.
uv run python manage.py migrate --fake-initial

# Collect static
echo "Collecting static files..."
uv run python manage.py collectstatic --noinput

# NOTE: scheduler runs as a separate process (`uv run python manage.py scheduler`),
# it is intentionally NOT started here because it blocks.

# Create superuser (interactive)
echo "Creating superuser (skip with Ctrl+C)..."
uv run python manage.py createsuperuser || true

# Start dev server
echo "Starting the server..."
uv run gunicorn core.wsgi:application -c script/gunicorn/gunicorn.conf.py
