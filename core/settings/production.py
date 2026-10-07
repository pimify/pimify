from decouple import config
from urllib.parse import urlparse
from .base import *
# NOTE: underscore-private, so not carried by the star import above.
from .base import _dbbackup_storage
from .base import _media_storage

# Debug is always False in production (ignore env to avoid accidents).
DEBUG = False

# Security setting (required in production; .env.example documents this).
SECRET_KEY = config("SECRET_KEY")

# Your domain as full origin, e.g. https://pimify.example.com
DOMAIN = config("DOMAIN", default="http://127.0.0.1:8000")

# Derive bare hostname for ALLOWED_HOSTS (DOMAIN may include scheme/port).
_DOMAIN_HOST = urlparse(DOMAIN).hostname or DOMAIN

# Hosts/domain names that Django site can serve
ALLOWED_HOSTS = [
    _DOMAIN_HOST,
]

# CSRF Settings
CSRF_COOKIE_NAME = 'csrf_token' # Variable name to store CSRF token
CSRF_COOKIE_PATH = '/' # Set the path
CSRF_COOKIE_SECURE = True  # Only send CSRF cookie over HTTPS
CSRF_COOKIE_HTTPONLY = True  # JavaScript can't access CSRF cookie
CSRF_COOKIE_SAMESITE = 'Strict'  # Strict CSRF cookie policy
CSRF_HEADER_NAME = 'HTTP_X_CSRFTOKEN' # HTTP header name to send CSRF token
CSRF_TRUSTED_ORIGINS = [
    DOMAIN,  # Must be full origin with scheme
]
CSRF_USE_SESSIONS = True  # Store CSRF token in session instead of cookie

# Session Settings
SESSION_COOKIE_SECURE = True  # Only send session cookie over HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
SESSION_COOKIE_SAMESITE = 'Strict'  # Strict same-site policy

# HTTP Strict Transport Security
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True  # Include subdomains in HSTS
SECURE_HSTS_PRELOAD = True  # Allow preloading of HSTS

# SSL/HTTPS Settings (Enable this setting in production)
# SECURE_SSL_REDIRECT = True  # Redirect all HTTP traffic to HTTPS
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security Headers
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'  # Prevent clickjacking
SECURE_BROWSER_XSS_FILTER = True  # Enable XSS filtering
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevent MIME type sniffing

# Cross-Origin Resource Sharing (CORS)
CORS_ALLOWED_ORIGINS = [
    DOMAIN,
]
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ['Content-Type', 'X-CSRFToken']

# NOTE: WhiteNoise middleware is already in base MIDDLEWARE — do not insert twice.

# Static files storage configuration (manifest variant for production)
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
    # Same env-gated media alias as base (local dir unless MEDIA_S3_BUCKET
    # or MEDIA_BASE_URL is set). NOTE: with DEBUG=False nothing serves
    # /media/ from Django — production must serve it via S3 or nginx.
    "default": _media_storage(),
    # Same env-gated alias as base (local dir unless DBBACKUP_S3_BUCKET set).
    "dbbackup": _dbbackup_storage(),
}

# WhiteNoise cache in prod: 60s. Browsers revalidate, so replaced images
# appear — no staleness bugs.
WHITENOISE_MAX_AGE = 60
