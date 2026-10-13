from .base import *  # noqa: F403

SECRET_KEY = "test-only-secret-key-that-is-at-least-32-bytes"
DEBUG = False
ALLOWED_HOSTS = ["testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
