# Pimify — two-stage OCI build on Debian slim (glibc).
#
# Why not alpine: the compiled deps (Pillow, orjson, pydantic-core, Brotli,
# fastnanoid) only resolve as manylinux wheels for cp314; on musl they would
# need a Rust/gcc toolchain in the image. Slim installs from wheels with no
# compiler. Why two stages: keep the final image free of uv (~35MB) — the
# entrypoint uses /app/.venv/bin directly, so boot resolves nothing.
#
# CRITICAL: the venv must live at /app/.venv in BOTH stages. Console
# shebangs are absolute (#!/app/.venv/bin/python), so a different path in
# the final stage breaks every entrypoint script.

# --------------------------------------------------------------------------
# Stage 1: builder — Python + locked deps into /app/.venv
# --------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

# uv binary, pinned (a moving `latest` tag makes builds non-reproducible).
COPY --from=ghcr.io/astral-sh/uv:0.9.16 /uv /bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md /app/

# Locked deps only, no dev packages. [tool.uv] package = false means there
# is no project to install (--no-install-project would be a no-op).
RUN uv sync --locked --no-dev

# --------------------------------------------------------------------------
# Stage 2: runtime — slim + venv + source, no uv, no toolchain
# --------------------------------------------------------------------------
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create a non-root user (Debian useradd, not busybox adduser).
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --create-home \
        --home-dir /home/appuser --shell /usr/sbin/nologin appuser

# venv must land at the SAME absolute path as in the builder (shebangs).
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

WORKDIR /app

# Source + gunicorn config baked in (collectstatic runs at container start,
# because manifest staticfiles depend on the same settings file).
# NOTE: runtime dirs (/app/data etc.) are created here as root (COPY skips
# them — data/, backups/, media/, static/ are dockerignored), so they must
# be chown'd to appuser: appuser can't write root-owned dirs, which surfaces
# as sqlite3 "unable to open database file". chmod alone is not enough.
COPY --chown=appuser:appgroup . /app
RUN mkdir -p /etc/gunicorn /app/data /app/backups /app/media /app/static /app/feeds && \
    cp /app/script/gunicorn/gunicorn.conf.py /etc/gunicorn/gunicorn.conf.py && \
    chmod +x /app/script/start/install.oci.sh && \
    chown -R appuser:appgroup /app/data /app/backups /app/media /app/static /app/feeds && \
    chmod -R 755 /app/data /app/backups /app/media

# Stay non-root
USER appuser

ENTRYPOINT ["sh", "script/start/install.oci.sh"]
