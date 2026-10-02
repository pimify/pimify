# Import necessary modules
from decouple import config
from pathlib import Path
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.templatetags.static import static

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Open exchange rate app id (empty disables exchange-rate jobs)
OPEN_EXCHANGE_RATES_APP_ID = config("OPEN_EXCHANGE_RATES_APP_ID", default="")

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
    'djmoney.contrib.exchange',
    'django_apscheduler',
    'dbbackup',
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

# Django Money backend config
DJANGO_MONEY_RATES = {
    'DEFAULT_BACKEND': 'djmoney.contrib.exchange.backends.OpenExchangeRatesBackend',
    'OPEN_EXCHANGE_RATES_URL': "https://openexchangerates.org/api/latest.json",
}

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

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "LOCATION": MEDIA_ROOT,
    },
}

# STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

# Backup settings
def db_backup_filename(databasename, servername, datetime, extension, content_type):
    return f"db_{datetime}.{extension}"

def media_backup_filename(databasename, servername, datetime, extension, content_type):
    return f"media_{datetime}.{extension}"

DBBACKUP_STORAGE = 'django.core.files.storage.FileSystemStorage'
DBBACKUP_STORAGE_OPTIONS = {'location': BASE_DIR / '../backups'}
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
            # Product management section
            {
                "title": _("Product Management"),
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
            # Stock management section — Phase 1 (pure-PIM pivot): hidden, not
            # part of the PIM surface. Uncommented only if the WMS plugin UI
            # is needed. Models still live in api/ this release.
            # {
            #     "title": _("Stock Management"),
            #     "separator": False,
            #     "collapsible": False,
            #     "items": [
            #         {
            #             "title": _("Suppliers"),
            #             "icon": "local_shipping",
            #             "link": reverse_lazy("admin:api_supplier_changelist"),
            #             "permission": lambda request: request.user.is_staff,
            #         },
            #         {
            #             "title": _("Warehouses"),
            #             "icon": "warehouse",
            #             "link": reverse_lazy("admin:api_warehouse_changelist"),
            #             "permission": lambda request: request.user.is_staff,
            #         },
            #         {
            #             "title": _("Stocks"),
            #             "icon": "inventory",
            #             "link": reverse_lazy("admin:api_stock_changelist"),
            #             "permission": lambda request: request.user.is_staff,
            #         },
            #         {
            #             "title": _("Product Suppliers"),
            #             "icon": "compare_arrows",
            #             "link": reverse_lazy("admin:api_productsupplier_changelist"),
            #             "permission": lambda request: request.user.is_staff,
            #         },
            #     ],
            # },
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