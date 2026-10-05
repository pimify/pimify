# Import necessary modules
from decouple import config
from pathlib import Path
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Define application categories
LOCAL_APPS = [
    'api',
    'catalog',      # Phase 2: pure-PIM domain (placeholder during Phase 1)
    'inventory',    # Phase 1: WMS read mirror — unmanaged models sharing api tables
    'procurement',  # Phase 1: procurement read mirror — unmanaged models sharing api tables
]

# Third-party applications
THIRD_PARTY_APPS = [
    'import_export',
    'image_uploader_widget',
    'login_history',
    'djmoney',
    'django_apscheduler',
    'dbbackup',
    'simple_history',  # Phase 2: Product/Variant/Value audit trail (Unfold-native)
]

# Admin theme and related apps
THIRD_PARTY_ADMIN_APPS = [
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'unfold.contrib.import_export',
]

# Combine all apps
INSTALLED_APPS = [
    *THIRD_PARTY_ADMIN_APPS,
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    *THIRD_PARTY_APPS,
    *LOCAL_APPS,
]

# Middleware configuration
MIDDLEWARE = [
    "core.compressor.middleware.BrotliMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # For serving static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "api.middleware.DeprecationMiddleware",  # Phase 1: Sunset headers on non-PIM endpoints
]

# URL configuration
ROOT_URLCONF = "core.urls"

# Template configuration
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "../templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# WSGI and ASGI configuration
WSGI_APPLICATION = "core.wsgi.application"

# Database configuration using SQLite
# NOTE: OPTIONS takes a single init_command — merge both PRAGMAs into one.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / "../data/db.sqlite3",
        "OPTIONS": {
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous = NORMAL;",
            "timeout": 20,
        },
    }
}

# Password validation settings
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization settings
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static and media files configuration
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / '../static'
STATICFILES_DIRS = [BASE_DIR / '../static_src']
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / '../media'

# Phase 4 outbound feeds: rendered files land here, served by the runs
# download endpoint (pull model). Local dir; off-site happens by fetching.
FEEDS_ROOT = BASE_DIR / '../feeds'

def _dbbackup_storage():
    """Backup storage alias: local dir unless S3 is configured (defined before
    STORAGES because the dict literal calls it). Credentials come from the
    standard AWS env chain, never from settings."""
    bucket = config("DBBACKUP_S3_BUCKET", default="")
    if not bucket:
        return {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": BASE_DIR / "../backups"},
        }
    options = {"bucket_name": bucket}
    endpoint = config("DBBACKUP_S3_ENDPOINT_URL", default="")
    if endpoint:
        options["endpoint_url"] = endpoint  # MinIO / S3-compatible API
    region = config("DBBACKUP_S3_REGION", default="")
    if region:
        options["region_name"] = region
    prefix = config("DBBACKUP_S3_PREFIX", default="pimify/")
    if prefix:
        options["location"] = prefix
    return {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": options}


STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "LOCATION": MEDIA_ROOT,
    },
    # django-dbbackup >= 5 reads STORAGES["dbbackup"] (the old
    # DBBACKUP_STORAGE[_OPTIONS] settings raise RuntimeError there).
    # Local filesystem by default; S3 when DBBACKUP_S3_BUCKET is set.
    # Credentials come from the standard AWS env chain (AWS_ACCESS_KEY_ID /
    # AWS_SECRET_ACCESS_KEY), so they are never written into settings.
    "dbbackup": _dbbackup_storage(),
}

# STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

# Backup settings
def db_backup_filename(databasename, servername, datetime, extension, content_type):
    return f"db_{datetime}.{extension}"

def media_backup_filename(databasename, servername, datetime, extension, content_type):
    return f"media_{datetime}.{extension}"

DBBACKUP_TMP_FILE_MAX_SIZE = 10*1024*1024
DBBACKUP_CLEANUP_KEEP = config("DBBACKUP_CLEANUP_KEEP", default=3, cast=int)
DBBACKUP_CLEANUP_KEEP_MEDIA = config("DBBACKUP_CLEANUP_KEEP_MEDIA", default=3, cast=int)
DBBACKUP_FILENAME_TEMPLATE = db_backup_filename
DBBACKUP_MEDIA_FILENAME_TEMPLATE = media_backup_filename

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Unfold admin theme configuration
UNFOLD = {
    # Basic site configuration
    "SITE_TITLE": "Pimify",
    "SITE_HEADER": "Pimify",
    "SITE_SYMBOL": "package",
    "THEME": "dark",
    "DASHBOARD_CALLBACK": "api.views.dashboard_callback",
    
    # Site icons and styling
    "SITE_ICON": {
        "light": lambda request: static("img/favicon.ico"), 
        "dark": lambda request: static("img/favicon.ico"),  
    },
    "SITE_FAVICONS": [
        {
            "rel": "icon",
            "href": lambda request: static("img/favicon.ico"),
        },
    ],
    "STYLES": [
        lambda request: static("dashboard/css/styles.css"),
    ],
    
    # Color configuration
    "COLORS": {
        "font": {
            "subtle-light": "107 114 128",
            "subtle-dark": "156 163 175",
            "default-light": "75 85 99",
            "default-dark": "209 213 219",
            "important-light": "17 24 39",
            "important-dark": "243 244 246",
        },
        "primary": {
            "50": "255 250 240",
            "100": "255 238 204",
            "200": "254 215 170",
            "300": "253 186 114",
            "400": "251 146 60",
            "500": "245 121 0",
            "600": "220 98 10",
            "700": "184 79 18",
            "800": "140 62 25",
            "900": "104 47 24",
            "950": "66 28 20"
        },
    },
    
    # Sidebar navigation configuration
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            # Dashboard section
            {
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Dashboard"),
                        "icon": "home",
                        "link": reverse_lazy("admin:index"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            # Legacy product section — Phase 2.3 audit: same concepts as
            # Catalog above but bound to the legacy api.* tables. Kept
            # reachable until the 1.4 cutover; the label marks it deprecated.
            {
                "title": _("Legacy (deprecated)"),
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Categories"),
                        "icon": "category",
                        "link": reverse_lazy("admin:api_category_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Products"),
                        "icon": "box",
                        "link": reverse_lazy("admin:api_product_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Product Images"),
                        "icon": "image",
                        "link": reverse_lazy("admin:api_productimage_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            # Catalog section — Phase 2.3: pure-PIM surface
            {
                "title": _("Catalog"),
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Products"),
                        "icon": "box",
                        "link": reverse_lazy("admin:catalog_product_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Families"),
                        "icon": "folder_managed",
                        "link": reverse_lazy("admin:catalog_attributeset_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Attributes"),
                        "icon": "tune",
                        "link": reverse_lazy("admin:catalog_attribute_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Categories"),
                        "icon": "category",
                        "link": reverse_lazy("admin:catalog_category_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Media"),
                        "icon": "image",
                        "link": reverse_lazy("admin:catalog_productmedia_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            # Syndication section — Phase 2.3: channels, locales, completeness
            {
                "title": _("Syndication"),
                "separator": False,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Channels"),
                        "icon": "send",
                        "link": reverse_lazy("admin:catalog_channel_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Locales"),
                        "icon": "translate",
                        "link": reverse_lazy("admin:catalog_locale_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                    {
                        "title": _("Completeness"),
                        "icon": "checklist",
                        "link": reverse_lazy("admin:catalog_completenessrule_changelist"),
                        "permission": lambda request: request.user.is_staff,
                    },
                ],
            },
            # Settings section
            {
                "title": _("Settings"),
                "separator": True,
                "collapsible": False,
                "items": [
                    {
                        "title": _("Organization"),
                        "icon": "settings",
                        "link": reverse_lazy("admin:api_organization_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Users and Permissions"),
                        "icon": "manage_accounts",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    # {
                    #     "title": _("Scheduler"),
                    #     "icon": "schedule",
                    #     "link": reverse_lazy("admin:django_apscheduler_djangojobexecution_changelist"),
                    #     "permission": lambda request: request.user.is_superuser,
                    # },
                    {
                        "title": _("Logs"),
                        "icon": "monitoring",
                        "link": reverse_lazy("admin:login_history_loginhistory_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
    
    # Tab configuration for different sections
    "TABS": [
        # Organization and API settings tab
        {
            "models": [
                "api.organization",
                "api.apikey",
                "django_apscheduler.djangojobexecution",
                "django_apscheduler.djangojob",
            ],
            "items": [
                {
                    "title": _("Organization Details"),
                    "link": reverse_lazy("admin:api_organization_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("API Keys"),
                    "link": reverse_lazy("admin:api_apikey_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Scheduled Jobs"),
                    "link": reverse_lazy("admin:django_apscheduler_djangojob_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Job Executions"),
                    "link": reverse_lazy("admin:django_apscheduler_djangojobexecution_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
        # User management tab
        {
            "models": [
                "auth.user",
                "auth.group",
            ],
            "items": [
                {
                    "title": _("Users"),
                    "link": reverse_lazy("admin:auth_user_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
                {
                    "title": _("Groups"),
                    "link": reverse_lazy("admin:auth_group_changelist"),
                    "permission": lambda request: request.user.is_superuser,
                },
            ],
        },
    ],
}