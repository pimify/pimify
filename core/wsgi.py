import os
from decouple import config
from django.core.wsgi import get_wsgi_application

# Respect MODE like manage.py; fall back to development so `core.settings`
# (an empty package) is never used as the settings module.
MODE = config("MODE", default="development")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"core.settings.{MODE}")

# Create the WSGI application.
application = get_wsgi_application()

