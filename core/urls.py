# Import necessary modules
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

from api.main import app

urlpatterns = [
    # Redirect root URL to dashboard
    path('', lambda request: redirect('dashboard/', permanent=True)),
    
    # Admin dashboard URL (using Django's admin site)
    path('dashboard/', admin.site.urls),
    
    # API endpoints (version 1)
    path('api/v1/', app.urls),
]

# NOTE: the scheduler is started explicitly via `manage.py scheduler`
# (separate process) — never auto-started on import (it blocks).

# Serve static and media files in development
if settings.DEBUG:
    # Serve static files (CSS, JavaScript, etc.)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
    # Serve media files (user-uploaded content)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)