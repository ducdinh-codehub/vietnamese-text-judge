import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "judge",
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

ROOT_URLCONF = "judge_site.urls"

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
            ]
        },
    },
]

WSGI_APPLICATION = "judge_site.wsgi.application"

# The checkers store nothing. The database holds livestream comments and the accounts of the
# people allowed to work through the order queue (see README: migrate, createsuperuser).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Demo mode: every visitor gets the moderator features without logging in: the queue, hidden
# comments and why they were hidden, and "Làm lại từ đầu". Their own messages are still checked.
# Set LAYA_LIVE_DEMO=0 before putting the site online, or any visitor can read and wipe the chat.
LIVE_DEMO = os.environ.get("LAYA_LIVE_DEMO", "1") == "1"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "live_queue"
LOGOUT_REDIRECT_URL = "live"

# Reject request bodies over 32 KB before reading them. 3,000 characters of JSON-escaped
# Vietnamese is at most about 18 KB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 32 * 1024

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
