"""Per-environment config resolution (.env.dev / .env.prod).

MODE comes from the REAL OS environment only — never from an env file —
because the file is selected BY the mode (reading a file to learn which
file to read is the chicken-and-egg this module exists to avoid).

Precedence for every key: OS environ > selected env file > code default
(python-decouple already prefers os.environ over the repository).

Missing-file policy:
  development (.env.dev absent) -> bare defaults; a fresh clone must work
      with zero setup.
  production (.env.prod absent) -> ImproperlyConfigured; prod must never
      boot silently on defaults.
PIMIFY_ENV_FILE overrides the path (tests point it at a temp file).
"""
import os
from pathlib import Path

from decouple import Config, RepositoryEmpty, RepositoryEnv
from django.core.exceptions import ImproperlyConfigured

# Project root: core/settings/env.py -> core/settings -> core -> root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MODE = os.environ.get("MODE", "development")

# Short env-file names; DJANGO_SETTINGS_MODULE keeps the long module names
# (core.settings.development / core.settings.production). Staging is a
# one-line addition here.
MODE_TO_ENV_FILE = {
    "development": ".env.dev",
    "production": ".env.prod",
}

try:
    ENV_FILE_NAME = MODE_TO_ENV_FILE[MODE]
except KeyError:
    raise ImproperlyConfigured(
        f"Unknown MODE={MODE!r}; expected one of "
        f"{sorted(MODE_TO_ENV_FILE)} (set it in the OS environment)."
    )

_ENV_FILE = Path(os.environ.get("PIMIFY_ENV_FILE", PROJECT_ROOT / ENV_FILE_NAME))

if _ENV_FILE.is_file():
    config = Config(RepositoryEnv(str(_ENV_FILE)))
elif MODE == "production":
    if "PIMIFY_ENV_FILE" in os.environ:
        raise ImproperlyConfigured(
            f"PIMIFY_ENV_FILE={os.environ['PIMIFY_ENV_FILE']!r} does not exist."
        )
    if "SECRET_KEY" not in os.environ:
        raise ImproperlyConfigured(
            f"{ENV_FILE_NAME} not found at project root. Production refuses to "
            f"boot on defaults — run script/deploy/install.sh, which creates it."
        )
    # Container-style: no file, but the required values come from the real
    # environment (--env-file / -e / Environment=). Proceed on environ alone;
    # the SECRET_KEY guard below still validates strength.
    config = Config(RepositoryEmpty())
else:
    config = Config(RepositoryEmpty())


# Production secret guard: presence is not enough. Reject the public dev
# dummy, the shipped placeholder, and anything short. A forgeable SECRET_KEY
# means forgeable sessions/CSRF — fail the boot, not the request.
_KNOWN_BAD_SECRETS = frozenset({
    "dummy_secret123",  # development.py default, in public git history
    "change-me-to-a-strong-secret",  # shipped .env.prod.example placeholder
    "secret_key",
})
_MIN_SECRET_LENGTH = 32


def require_production_secret(secret):
    """Raise ImproperlyConfigured unless `secret` is safe for production."""
    if not secret or secret in _KNOWN_BAD_SECRETS or len(secret) < _MIN_SECRET_LENGTH:
        raise ImproperlyConfigured(
            "Refusing to boot production with a missing, placeholder, or "
            f"short SECRET_KEY (need >= {_MIN_SECRET_LENGTH} chars). Generate one:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )
    return secret
