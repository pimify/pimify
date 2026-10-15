#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# MODE comes from the REAL OS environment only (never from an env file):
# it selects which file core/settings/env.py reads. Defaults to development
# so `manage.py` works on a fresh clone with zero setup.
MODE = os.environ.get("MODE", "development")

def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"core.settings.{MODE}")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
