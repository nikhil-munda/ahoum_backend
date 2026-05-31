from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Print emails to console in development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
