#!/bin/bash
# Pimify dev setup (uv). Run from project root.
set -e

# Dev tier, always: pin MODE so a stray exported MODE=production from other
# work can't boot prod settings here. Prod has its own script (script/deploy/).
export MODE=development

# Check for uv (install from https://docs.astral.sh/uv/ if missing)
if ! command -v uv &>/dev/null; then
    echo "uv is not installed. Install it first: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Sync locked dependencies (creates .venv on first run)
echo "Syncing dependencies with uv..."
uv sync --locked

# Ensure .env.dev exists (MODE=development reads .env.dev; see core/settings/env.py)
if [ ! -f .env.dev ]; then
    echo "Creating .env.dev from .env.dev.example..."
    cp .env.dev.example .env.dev
fi

# Create data/backup/media/feeds dirs
echo "Creating data, backups, media and feeds directories..."
mkdir -p data backups media feeds

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

# NOTE: scheduler runs as a separate long-lived process
# (`uv run python manage.py scheduler` — stays in the foreground until
# SIGTERM/SIGINT). It is intentionally NOT started here because it never
# returns; run it under a supervisor (see script/deploy/) or systemd.

# Create superuser (interactive)
echo "Creating superuser (skip with Ctrl+C)..."
uv run python manage.py createsuperuser || true

# Start dev server (Django runserver, not gunicorn: autoreload for the dev
# loop, and identical on macOS/Linux/Windows — gunicorn can't run on
# Windows, so it belongs to the prod paths only).
echo "Starting the server..."
uv run python manage.py runserver
