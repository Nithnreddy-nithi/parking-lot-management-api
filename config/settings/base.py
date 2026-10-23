import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-key")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.accounts.apps.AccountsConfig",
    "apps.parking.apps.ParkingConfig",
    "apps.sessions.apps.SessionsConfig",
    "apps.pricing.apps.PricingConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.reporting.apps.ReportingConfig",
    "apps.audit.apps.AuditConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "parking_lot"),
        "USER": os.getenv("POSTGRES_USER", "parking_lot"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "parking_lot"),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "parking_accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "config.api.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth_register": os.getenv("AUTH_REGISTER_THROTTLE_RATE", "5/hour"),
        "auth_token": os.getenv("AUTH_TOKEN_THROTTLE_RATE", "10/minute"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Parking Lot Management API",
    "DESCRIPTION": (
        "Parking Lot Management modular-monolith API. Authenticate with a JWT Bearer access token "
        "for protected operations."
    ),
    "VERSION": "6.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "ENUM_NAME_OVERRIDES": {
        "UserRole": "apps.accounts.models.User.Role",
        "ManageableUserRole": ["CUSTOMER", "OPERATOR"],
        "ParkingSessionStatus": "apps.sessions.enums.SessionStatus",
        "PricingCurrency": "apps.pricing.enums.Currency",
        "PricingCalculatorVersion": "apps.pricing.enums.CalculatorVersion",
        "PaymentStatus": "apps.payments.enums.PaymentStatus",
        "PaymentProvider": "apps.payments.enums.PaymentProviderName",
        "SettlementMethod": "apps.payments.enums.SettlementMethod",
    },
}

SIMULATED_PAYMENT_SCENARIO = os.getenv("SIMULATED_PAYMENT_SCENARIO", "SUCCESS")
