"""
Django settings for the wedding project.

All deployment- and person-specific values come from environment variables
(see ``.env.example``). Free-form text and images live in the optional content
overlay directory (``SITE_CONTENT_DIR``) so that nothing private is committed.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Load KEY=VALUE lines from a .env file without overriding variables already set."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


load_env_file(BASE_DIR / ".env")


def env_str(name, default=""):
    return os.environ.get(name, default).strip()


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean (true/false), got {value!r}")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)

SECRET_KEY = env_str("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY must be set when DEBUG is off")
    SECRET_KEY = "insecure-development-key"  # noqa: S105

# Public URL of the site, e.g. https://wedding.example.org (used in e-mails and for CSRF).
SITE_URL = env_str("SITE_URL", "http://localhost:8000").rstrip("/")

# localhost is always allowed so that the container healthcheck works.
ALLOWED_HOSTS = [*env_list("ALLOWED_HOSTS"), "localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", SITE_URL if SITE_URL.startswith("https://") else "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "crispy_forms",
    "crispy_bootstrap4",
    "guests",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bigday.urls"
WSGI_APPLICATION = "bigday.wsgi.application"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"
AUTH_USER_MODEL = "guests.Guest"
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap4"
CRISPY_TEMPLATE_PACK = "bootstrap4"

# Optional private overlay: templates/ and static/ placed in this directory take precedence over the
# defaults shipped in the repository (welcome text, e-mail copy, photos...).
SITE_CONTENT_DIR = Path(env_str("SITE_CONTENT_DIR", str(BASE_DIR / "content")))

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [SITE_CONTENT_DIR / "templates", BASE_DIR / "bigday" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "bigday.context_processors.site",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env_str("DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = env_str("LANGUAGE_CODE", "fr-fr")
TIME_ZONE = env_str("TIME_ZONE", "Europe/Paris")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = Path(env_str("STATIC_ROOT", str(BASE_DIR / "static_root")))
STATICFILES_DIRS = [path for path in (SITE_CONTENT_DIR / "static", BASE_DIR / "bigday" / "static") if path.is_dir()]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Site identity (all optional, neutral defaults) -------------------------------------------
COUPLE_NAMES = env_str("COUPLE_NAMES", "Les mariés")
SITE_TITLE = env_str("SITE_TITLE", "Notre mariage")
# Free text shown on the RSVP page and in e-mails, e.g. "le 15 mai" (empty = nothing).
RSVP_DEADLINE = env_str("RSVP_DEADLINE")
# Optional link to a gift pot, shown in the default gifts section.
GIFT_POT_URL = env_str("GIFT_POT_URL")
# Full-width hero image at the top of the site, relative to the static dirs (empty = none).
HEADER_IMAGE = env_str("HEADER_IMAGE")
# "cover" fills the whole band (crops), "contain" shows the whole image on a black background.
HEADER_IMAGE_FIT = env_str("HEADER_IMAGE_FIT", "cover")
if HEADER_IMAGE_FIT not in {"cover", "contain"}:
    raise ImproperlyConfigured("HEADER_IMAGE_FIT must be 'cover' or 'contain'")
# Images embedded in e-mails, relative to the static dirs (e.g. wedding/hero.jpg). Empty = no image.
EMAIL_HERO_IMAGE = env_str("EMAIL_HERO_IMAGE")
EMAIL_HEADER_IMAGE = env_str("EMAIL_HEADER_IMAGE")
# E-mail subjects; "{event}" is replaced by the name of the event.
SAVE_THE_DATE_SUBJECT = env_str("SAVE_THE_DATE_SUBJECT", "Save the date - {event}")
INVITATION_SUBJECT = env_str("INVITATION_SUBJECT", "Invitation - {event}")
PREPARATION_SUBJECT = env_str("PREPARATION_SUBJECT", "Quelques précisions - {event}")
THANK_YOU_SUBJECT = env_str("THANK_YOU_SUBJECT", "Merci ! - {event}")

# Guests without a personal link must know this phrase to create an account. Disabled when empty.
REGISTRATION_CODE = env_str("REGISTRATION_CODE")

# --- Photo gallery (optional Lychee server, https://lycheeorg.dev) -------------------------------
# Base URL of the gallery, e.g. https://wedding.example.org/photos (same host as the site so that the
# log-in cookies are shared). The photo features are hidden when empty.
LYCHEE_URL = env_str("LYCHEE_URL").rstrip("/")
# Where the server itself reaches the gallery API (e.g. http://192.168.1.20 on the LAN); defaults to LYCHEE_URL.
LYCHEE_API_URL = env_str("LYCHEE_API_URL", LYCHEE_URL).rstrip("/")
LYCHEE_ADMIN_USER = env_str("LYCHEE_ADMIN_USER")
LYCHEE_ADMIN_PASSWORD = os.environ.get("LYCHEE_ADMIN_PASSWORD", "")

# --- E-mail ------------------------------------------------------------------------------------
EMAIL_BACKEND = env_str("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env_str("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env_str("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = env_str("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_TIMEOUT = 30
DEFAULT_FROM_EMAIL = env_str("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "wedding@localhost")
# Reply-To and contact address shown on the site.
WEDDING_REPLY_EMAIL = env_str("REPLY_TO_EMAIL", EMAIL_HOST_USER)
# Addresses put in copy of every campaign e-mail.
WEDDING_CC_LIST = env_list("CC_LIST")

# --- Security ----------------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)  # TLS is normally terminated by the proxy
    SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE", SITE_URL.startswith("https://"))
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_HSTS_SECONDS = int(env_str("HSTS_SECONDS", "31536000" if SESSION_COOKIE_SECURE else "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_CONTENT_TYPE_NOSNIFF = True
# Personal links contain a secret token: never leak them through the Referer header.
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

# TLS (redirect, HSTS preload/subdomains) is handled by the reverse proxy in front of the container.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env_str("LOG_LEVEL", "INFO")},
}
