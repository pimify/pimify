#!/bin/bash
# Pimify VPS deploy. Run from the project root on the target host.
#
# Usage:
#   sudo script/deploy/install.sh [--supervisor systemd|supervisor|none]
#     [--proxy nginx|caddy|traefik|none] [--domain https://example.com]
#     [--app-dir /srv/pimify] [--app-user pimify] [--dry-run]
#
# Ownership model (prod): the deploy user owns code + .venv (read-only for
# the service); APP_USER owns data/media/backups/feeds/static (written at
# runtime). Commands that write data run AS the service user, so root never
# creates files the service can't write — the root-owned-db class of bug.
#
# What it does, in order:
#   0. .env.prod check (migrate legacy .env), refuse placeholder secrets.
#      No MODE gate: this script IS production, so it exports
#      MODE=production for the spine (Django reads MODE from the OS
#      environment, never from the file). Real enforcement is the
#      SECRET_KEY guard in core/settings/env.py, not a file line.
#   1. create the unprivileged service user
#   2. uv sync (as you) + makemigrations --check; migrate + collectstatic
#      AS the service user; chown -R the runtime dirs (upgrade repair)
#   3. pre-flight: prove the service user can read .env.prod, execute the
#      venv, and WRITE data/ — abort here, not mysteriously at runtime
#   4. render + install the chosen supervisor units and proxy config
#      (sets TRUST_PROXY_HEADERS=true in .env.prod when a proxy is used)
#   5. print the exact commands to enable everything
#
# --dry-run prints every action and writes nothing. With all flags supplied
# it runs fully non-interactive (CI-safe). Privileged steps need root —
# run under sudo, or the script re-execs the privileged parts via sudo.
set -euo pipefail

SUPERVISOR="systemd"
PROXY="none"
DOMAIN=""
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_USER="pimify"
DRY_RUN="0"

while [ $# -gt 0 ]; do
    case "$1" in
        --supervisor) SUPERVISOR="$2"; shift 2 ;;
        --proxy) PROXY="$2"; shift 2 ;;
        --domain) DOMAIN="$2"; shift 2 ;;
        --app-dir) APP_DIR="$2"; shift 2 ;;
        --app-user) APP_USER="$2"; shift 2 ;;
        --dry-run) DRY_RUN="1"; shift ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

case "$SUPERVISOR" in systemd|supervisor|none) ;; *)
    echo "--supervisor must be systemd|supervisor|none" >&2; exit 1 ;; esac
case "$PROXY" in nginx|caddy|traefik|none) ;; *)
    echo "--proxy must be nginx|caddy|traefik|none" >&2; exit 1 ;; esac

log()  { echo "==> $*"; }
dry()  { echo "    [dry-run] $*"; }

# Privileged runner: executes directly as root, else via sudo, else (dry-run)
# just prints. Fails loudly when neither is available.
priv() {
    if [ "$DRY_RUN" = "1" ]; then dry "$*"; return 0; fi
    if [ "$(id -u)" = "0" ]; then "$@"
    elif command -v sudo >/dev/null; then sudo "$@"
    else echo "Need root for: $* (re-run under sudo)" >&2; exit 1; fi
}

# Run a command AS the service user. `uv` is deliberately NOT used here:
# units call .venv/bin/python directly, so no HOME/cache is needed — but
# set HOME=/tmp anyway in case a tool looks for one (pimify has no home).
run_as() {
    if [ "$DRY_RUN" = "1" ]; then dry "sudo -u $APP_USER $*"; return 0; fi
    if [ "$(id -un)" = "$APP_USER" ]; then "$@"
    elif [ "$(id -u)" = "0" ]; then sudo -u "$APP_USER" env HOME=/tmp "$@"
    elif command -v sudo >/dev/null; then sudo -u "$APP_USER" env HOME=/tmp "$@"
    else echo "Cannot run as $APP_USER (no sudo). Re-run under sudo." >&2; exit 1; fi
}

# Set KEY=VALUE in .env.prod (replace if present, append if not).
set_env() {
    if [ "$DRY_RUN" = "1" ]; then dry "set $1=$2 in $APP_DIR/.env.prod"; return 0; fi
    if grep -q "^$1=" "$APP_DIR/.env.prod"; then
        sed -i "s|^$1=.*|$1=$2|" "$APP_DIR/.env.prod"
    else
        printf '%s=%s\n' "$1" "$2" >> "$APP_DIR/.env.prod"
    fi
}

TEMPLATE_DIR="$APP_DIR/script/deploy"

# --- 0. Preconditions -------------------------------------------------------
if ! command -v uv >/dev/null; then
    echo "uv is not installed: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi
if [ ! -f "$APP_DIR/pyproject.toml" ]; then
    echo "--app-dir must point at the Pimify checkout ($APP_DIR has no pyproject.toml)" >&2
    exit 1
fi
# Legacy single .env: migrate it once (it holds the real secret), then it is
# no longer read — MODE=production reads .env.prod. See core/settings/env.py.
if [ ! -f "$APP_DIR/.env.prod" ] && [ -f "$APP_DIR/.env" ]; then
    log "Migrating legacy .env -> .env.prod (your real secret moves with it)."
    [ "$DRY_RUN" = "1" ] && dry "cp $APP_DIR/.env $APP_DIR/.env.prod" \
        || cp "$APP_DIR/.env" "$APP_DIR/.env.prod"
fi
if [ ! -f "$APP_DIR/.env.prod" ]; then
    log "Creating .env.prod from .env.prod.example — EDIT IT before going live."
    [ "$DRY_RUN" = "1" ] && dry "cp $APP_DIR/.env.prod.example $APP_DIR/.env.prod" \
        || cp "$APP_DIR/.env.prod.example" "$APP_DIR/.env.prod"
fi
if grep -qE "^(SECRET_KEY=(change-me-to-a-strong-secret|dummy_secret123|secret_key)|SECRET_KEY=$)" "$APP_DIR/.env.prod" 2>/dev/null; then
    echo "Refusing: SECRET_KEY in .env.prod is a placeholder/dummy. Set a real one first:" >&2
    echo '  python -c "import secrets; print(secrets.token_urlsafe(64))"' >&2
    exit 1
fi
APP_MODE="$(grep -E '^MODE=' "$APP_DIR/.env.prod" 2>/dev/null | cut -d= -f2 | tr -d ' ' || true)"
if [ "$APP_MODE" != "production" ]; then
    echo "NOTE: MODE=$APP_MODE in .env.prod is documentation only — this script" >&2
    echo "IS the production path, so the spine below runs with MODE=production" >&2
    echo "exported regardless (Django reads MODE from the OS environment, never" >&2
    echo "from the file; see core/settings/env.py)." >&2
fi
# Single source of truth: this script deploys production, period. Export so
# the direct-run spine (uv sync, makemigrations check) uses prod settings;
# the sudo path passes MODE=production per command since sudo strips env.
export MODE=production
# Proxy needs a domain: explicit flag wins, else .env.prod DOMAIN.
if [ "$PROXY" != "none" ] && [ -z "$DOMAIN" ]; then
    DOMAIN="$(grep -E '^DOMAIN=' "$APP_DIR/.env.prod" | cut -d= -f2- | tr -d ' ' || true)"
fi
if [ "$PROXY" != "none" ] && [ -z "$DOMAIN" ]; then
    echo "--proxy $PROXY needs --domain (or DOMAIN in .env.prod)" >&2; exit 1
fi
# Bare host for server_name / Host() rules: strip scheme, path and port.
DOMAIN_HOST="$(echo "$DOMAIN" | sed -e 's|^[a-z]*://||' -e 's|/.*||' -e 's|:.*||')"

# --- 1. Service user (before the spine, which runs as it) -------------------
log "Ensuring service user '$APP_USER' exists (no login shell)..."
if id "$APP_USER" >/dev/null 2>&1; then
    [ "$DRY_RUN" = "1" ] && dry "(user $APP_USER already exists)"
else
    priv useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# --- 2. App spine ------------------------------------------------------------
cd "$APP_DIR"
log "Syncing dependencies with uv (as you; the service only reads .venv)..."
[ "$DRY_RUN" = "1" ] && dry "uv sync --locked" || uv sync --locked
log "Checking for missing migrations..."
[ "$DRY_RUN" = "1" ] && dry "uv run python manage.py makemigrations --check --dry-run" \
    || uv run python manage.py makemigrations --check --dry-run
# migrate + collectstatic WRITE data/ and static/ — run as the service user
# so the files are born with the right owner (never root-owned).
log "Running migrations as $APP_USER..."
run_as env MODE=production "$APP_DIR/.venv/bin/python" manage.py migrate --fake-initial
log "Collecting static files as $APP_USER..."
run_as env MODE=production "$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput

# --- 3. Ownership repair + pre-flight ---------------------------------------
log "Repairing ownership of runtime dirs (upgrades from root-created layouts)..."
for d in data media backups feeds static; do
    [ "$DRY_RUN" = "1" ] && dry "mkdir -p $APP_DIR/$d && chown -R $APP_USER:$APP_USER $APP_DIR/$d" \
        && continue
    mkdir -p "$APP_DIR/$d"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/$d"
done
log "Pre-flight: proving $APP_USER can actually run the app..."
if [ "$DRY_RUN" = "1" ]; then
    dry "sudo -u $APP_USER test -r .env.prod && test -x .venv/bin/python && touch data/.w && rm data/.w"
else
    run_as test -r "$APP_DIR/.env.prod" \
        || { echo "FAIL: $APP_USER cannot read .env.prod" >&2; exit 1; }
    run_as test -x "$APP_DIR/.venv/bin/python" \
        || { echo "FAIL: $APP_USER cannot execute the venv python" >&2; exit 1; }
    run_as touch "$APP_DIR/data/.deploy-write-test" \
        && run_as rm "$APP_DIR/data/.deploy-write-test" \
        || { echo "FAIL: $APP_USER cannot write $APP_DIR/data (SQLite would fail)" >&2; exit 1; }
    echo "    pre-flight OK: .env.prod readable, venv executable, data/ writable"
fi

render() {  # render <template> <dest>: substitute placeholders
    tmp="$(mktemp)"
    sed -e "s|__APP_DIR__|$APP_DIR|g" \
        -e "s|__APP_USER__|$APP_USER|g" \
        -e "s|__DOMAIN_HOST__|$DOMAIN_HOST|g" "$1" > "$tmp"
    if [ "$DRY_RUN" = "1" ]; then dry "render $1 -> $2"; rm -f "$tmp"; return 0; fi
    if [ -w "$(dirname "$2")" ]; then cp "$tmp" "$2"; else priv cp "$tmp" "$2"; fi
    rm -f "$tmp"
}

# --- 4. Supervisor units -----------------------------------------------------
case "$SUPERVISOR" in
    systemd)
        log "Installing systemd units..."
        render "$TEMPLATE_DIR/systemd/pimify-web.service" /etc/systemd/system/pimify-web.service
        render "$TEMPLATE_DIR/systemd/pimify-scheduler.service" /etc/systemd/system/pimify-scheduler.service
        ;;
    supervisor)
        log "Installing supervisor configs..."
        render "$TEMPLATE_DIR/supervisor/pimify-web.conf" /etc/supervisor/conf.d/pimify-web.conf
        render "$TEMPLATE_DIR/supervisor/pimify-scheduler.conf" /etc/supervisor/conf.d/pimify-scheduler.conf
        ;;
    none)
        log "Skipping supervisor (--supervisor none): units rendered under $APP_DIR for manual use."
        [ "$DRY_RUN" = "1" ] && dry "mkdir -p $APP_DIR/.deploy-out" \
            || mkdir -p "$APP_DIR/.deploy-out"
        [ "$DRY_RUN" != "1" ] && {
            render "$TEMPLATE_DIR/systemd/pimify-web.service" "$APP_DIR/.deploy-out/pimify-web.service"
            render "$TEMPLATE_DIR/systemd/pimify-scheduler.service" "$APP_DIR/.deploy-out/pimify-scheduler.service"
        }
        ;;
esac

# --- 5. Reverse proxy --------------------------------------------------------
# Any proxy here terminates TLS, so Django must believe X-Forwarded-Proto:
# the installer sets TRUST_PROXY_HEADERS itself (it knows a proxy exists).
if [ "$PROXY" != "none" ]; then
    log "Enabling TRUST_PROXY_HEADERS in .env.prod (TLS terminates at the proxy)..."
    set_env TRUST_PROXY_HEADERS true
fi
case "$PROXY" in
    nginx)
        log "Installing nginx site for $DOMAIN_HOST..."
        if [ -d /etc/nginx/sites-enabled ] || [ "$DRY_RUN" = "1" ]; then
            # Debian/Ubuntu layout. (dry-run assumes it; the real run checks.)
            render "$TEMPLATE_DIR/proxy/nginx-pimify.conf" /etc/nginx/sites-available/pimify.conf
            priv ln -sf /etc/nginx/sites-available/pimify.conf /etc/nginx/sites-enabled/pimify.conf
        else
            # RHEL-style: no sites-enabled, conf.d is included by default.
            render "$TEMPLATE_DIR/proxy/nginx-pimify.conf" /etc/nginx/conf.d/pimify.conf
        fi
        ;;
    caddy)
        log "Installing Caddy site for $DOMAIN_HOST (TLS is automatic)..."
        priv mkdir -p /etc/caddy/sites
        render "$TEMPLATE_DIR/proxy/Caddyfile-pimify" /etc/caddy/sites/pimify.caddy
        ;;
    traefik)
        log "Rendering Traefik dynamic config for $DOMAIN_HOST..."
        [ "$DRY_RUN" = "1" ] && dry "mkdir -p $APP_DIR/.deploy-out" \
            || mkdir -p "$APP_DIR/.deploy-out"
        [ "$DRY_RUN" != "1" ] && \
            render "$TEMPLATE_DIR/proxy/traefik-pimify.yml" "$APP_DIR/.deploy-out/traefik-pimify.yml"
        ;;
    none)
        log "Skipping reverse proxy (--proxy none): app listens on 127.0.0.1:8000 only."
        ;;
esac

# --- 6. Activation -----------------------------------------------------------
echo
echo "Done. Activate with:"
case "$SUPERVISOR" in
    systemd)
        echo "  systemctl daemon-reload"
        echo "  systemctl enable --now pimify-web pimify-scheduler"
        echo "  systemctl is-active pimify-web pimify-scheduler"
        ;;
    supervisor)
        echo "  supervisorctl reread && supervisorctl update"
        echo "  supervisorctl start pimify-web pimify-scheduler"
        echo "  supervisorctl status"
        ;;
    none)
        echo "  (manual: install the units from $APP_DIR/.deploy-out yourself)"
        ;;
esac
case "$PROXY" in
    nginx)
        echo "  nginx -t && systemctl reload nginx   # after certs exist:"
        echo "  certbot --nginx -d $DOMAIN_HOST"
        ;;
    caddy)
        echo "  systemctl reload caddy   # TLS certificates are automatic"
        ;;
    traefik)
        echo "  # load $APP_DIR/.deploy-out/traefik-pimify.yml via --providers.file,"
        echo "  # with entrypoints web/websecure and a 'le' certResolver in static config"
        ;;
esac
echo "  curl -I http://127.0.0.1:8000/api/v1/public/health   # expect 200"
