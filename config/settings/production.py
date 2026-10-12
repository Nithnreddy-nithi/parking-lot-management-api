import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"Required production environment variable {name} is missing")
    return value


SECRET_KEY = required_environment("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [
    host.strip() for host in required_environment("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()
]

for setting_name in (
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_HOST",
    "POSTGRES_PORT",
):
    required_environment(setting_name)

DATABASES["default"].update(  # noqa: F405
    {
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ["POSTGRES_HOST"],
        "PORT": os.environ["POSTGRES_PORT"],
    }
)

DEBUG = False
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
