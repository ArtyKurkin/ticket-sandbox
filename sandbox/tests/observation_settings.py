"""Isolated test DB, no .env reads, Sentry, broker, or real user database."""
import os
from unittest.mock import patch

with patch("dotenv.load_dotenv", return_value=False), patch.dict(os.environ, {"SENTRY_DSN": ""}):
    from config.settings import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
SANDBOX_HTTP_OBSERVATION_ENABLED = False
CELERY_BROKER_URL = "memory://"
SECURE_SSL_REDIRECT = False
STATIC_ROOT = BASE_DIR / "static"  # Existing checked-in Vite artifacts; no build.
STATICFILES_DIRS = []
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
