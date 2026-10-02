#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
from decouple import config
import os
import sys

# Get MODE from environment (defaults to development so `manage.py` works without .env)
MODE = config("MODE", default="development")

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
