FROM python:3.14-alpine

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_CACHE=1 \
    PATH="/home/appuser/.local/bin:$PATH"

# uv binary (pinned via official image)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Create a non-root user
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

# Set working directory; copy lockfiles first for layer caching
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md /app/
RUN mkdir -p /app/api /app/core && chown -R appuser:appgroup /app

USER appuser

# Install locked deps (no source yet — uses cache efficiently).
# NOTE: --no-install-project omitted: [tool.uv] package = false means there
# is no project to install, so the flag would be a no-op.
RUN uv sync --locked --no-dev

# Copy the rest of the source
COPY --chown=appuser:appgroup . /app

# Finish project install + prepare runtime dirs/config
RUN uv sync --locked --no-dev && \
    mkdir -p /etc/gunicorn /app/data /app/backups /app/media /app/static && \
    cp /app/script/gunicorn/gunicorn.conf.py /etc/gunicorn/gunicorn.conf.py && \
    chmod +x /app/script/start/install.oci.sh && \
    chmod -R 755 /app/data /app/backups /app/media

# Stay non-root
USER appuser

ENTRYPOINT ["sh", "script/start/install.oci.sh"]
