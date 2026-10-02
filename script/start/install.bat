@echo off
REM Pimify dev setup for Windows (uv). Run from project root.

where uv >nul
if errorlevel 1 (
    echo uv is not installed. Install it first: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

echo Syncing dependencies with uv...
uv sync --locked
if errorlevel 1 exit /b %errorlevel%

if not exist .env (
    echo Creating .env from .env.example...
    copy .env.example .env
)

echo Creating data, backups and media directories...
mkdir data 2>nul
mkdir backups 2>nul
mkdir media 2>nul

echo Checking for missing migrations...
uv run python manage.py makemigrations --check --dry-run

echo Running migrations...
REM --fake-initial: upgrades pre-uv installs whose api tables exist without a
REM recorded migration; fresh DBs migrate normally.
uv run python manage.py migrate --fake-initial

echo Collecting static files...
uv run python manage.py collectstatic --noinput

REM NOTE: scheduler is blocking - run `uv run python manage.py scheduler` separately.

echo Creating superuser (Ctrl+C to skip)...
uv run python manage.py createsuperuser

echo Starting the server...
uv run python manage.py runserver
