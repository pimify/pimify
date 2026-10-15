@echo off
REM Pimify dev setup for Windows (uv). Run from project root.

REM Dev tier, always: pin MODE so a stray MODE=production from other work
REM can't boot prod settings here. Prod has its own script (script/deploy/).
set MODE=development

where uv >nul
if errorlevel 1 (
    echo uv is not installed. Install it first: https://docs.astral.sh/uv/getting-started/installation/
    exit /b 1
)

echo Syncing dependencies with uv...
uv sync --locked
if errorlevel 1 exit /b %errorlevel%

if not exist .env.dev (
    echo Creating .env.dev from .env.dev.example...
    copy .env.dev.example .env.dev
)

echo Creating data, backups, media and feeds directories...
mkdir data 2>nul
mkdir backups 2>nul
mkdir media 2>nul
mkdir feeds 2>nul

echo Checking for missing migrations...
uv run python manage.py makemigrations --check --dry-run

echo Running migrations...
REM --fake-initial: upgrades pre-uv installs whose api tables exist without a
REM recorded migration; fresh DBs migrate normally.
uv run python manage.py migrate --fake-initial

echo Collecting static files...
uv run python manage.py collectstatic --noinput

REM NOTE: scheduler is long-lived - run `uv run python manage.py scheduler` separately.

echo Creating superuser - press Ctrl+C to skip...
REM NOTE: no parentheses in the fallback echo — unescaped parens break
REM batch parsing if this line ever lands inside a parenthesized block.
uv run python manage.py createsuperuser || echo skipped superuser creation, continuing...

echo Starting the server...
uv run python manage.py runserver
