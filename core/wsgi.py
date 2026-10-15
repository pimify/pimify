import os
from django.core.wsgi import get_wsgi_application

# MODE comes from the REAL OS environment only (never from an env file):
# it selects which file core/settings/env.py reads. Container/systemd
# units set it explicitly; local default is development.
MODE = os.environ.get("MODE", "development")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"core.settings.{MODE}")

# Create the WSGI application.
application = get_wsgi_application()

