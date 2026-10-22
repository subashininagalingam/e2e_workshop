import os
from pathlib import Path
import dj_database_url
import cloudinary

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=""):
    return os.environ.get(name, default).strip()


DEBUG = env("DEBUG", "False").lower() in ("1", "true", "yes")
SECRET_KEY = env("SECRET_KEY", "dev-only-insecure-key")
if not DEBUG and SECRET_KEY.startswith(("dev-only", "change-me")):
    raise ImproperlyConfigured(
        "Settings not found. Copy the file '.env.example' to a new file named '.env' "
        "(for local testing keep DEBUG=True; on a live server set a real SECRET_KEY)."
    )

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("CSRF_TRUSTED_ORIGINS").split(",") if o.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    'cloudinary',
    'cloudinary_storage',

    "workshops",
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

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "workshops.context_processors.site",
            ]
        },
    }
]

# Small database used ONLY for workshops and admin logins. Registrations are NOT stored here.
# DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DATABASES = {'default': dj_database_url.parse(os.environ.get("DATABASE_URL"))}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = False
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 4 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024

# ---- Where registrations are stored (the ONLY place) ----
DATA_DIR = BASE_DIR / "data"
REGISTRATIONS_XLSX = DATA_DIR / "registrations.xlsx"
# Payment screenshots are private: kept outside media/ and shown only to signed-in staff.
PAYMENTS_DIR = DATA_DIR / "payments"
MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024
# Certificate templates are private too (a blank template could be used to forge certificates).
CERT_TEMPLATES_DIR = DATA_DIR / "certificate_templates"
CERT_FONT_DIR = BASE_DIR / "static" / "fonts"   # drop any .ttf here and it appears in the certificate setup page
MAX_CERT_TEMPLATE_BYTES = 15 * 1024 * 1024
ANNOUNCE_FILES_DIR = DATA_DIR / "announce_files"   # brochures attached to announcement emails (private)
MAX_ANNOUNCE_FILE_BYTES = 5 * 1024 * 1024
MAX_ANNOUNCE_TOTAL_BYTES = 12 * 1024 * 1024        # Gmail refuses emails above about 25 MB in total
MAX_ANNOUNCE_FILES = 6
ANNOUNCE_BATCH = 40    # emails sent per click on "Send next batch" (keeps each request short)

# ---- Site / organisation ----
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
POST_SUBMIT_REDIRECT_URL = env("POST_SUBMIT_REDIRECT_URL", "https://errors2experts.com/")
ORG = {
    "name": env("ORG_NAME", "Errors2Experts IT Training & IT Services"),
    "short": env("ORG_SHORT_NAME", "Errors2Experts"),
    "website": env("ORG_WEBSITE", "https://errors2experts.com/"),
    "email": env("ORG_EMAIL", "errors2experts.official@gmail.com"),
    "phone": env("ORG_PHONE", "9363342646"),
    "phones": [p.strip() for p in env("ORG_PHONES", "9363342646,9043341503,8015306807").split(",") if p.strip()],
    "address": env("ORG_ADDRESS", "Dindigul, Tamil Nadu"),
    "registration": env("ORG_REGISTRATION", "MSME Registered (UDYAM-TN-06-0108008)"),
    "social": {
        k: env("SOCIAL_" + k.upper())
        for k in ("instagram", "linkedin", "youtube", "facebook", "whatsapp")
        if env("SOCIAL_" + k.upper())
    },
}

# ---- Email ----
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587") or 587)
EMAIL_USE_TLS = EMAIL_PORT != 465
EMAIL_USE_SSL = EMAIL_PORT == 465
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = f'{env("MAIL_FROM_NAME", "Errors2Experts")} <{EMAIL_HOST_USER or "noreply@example.com"}>'
ADMIN_NOTIFY_EMAIL = env("ADMIN_NOTIFY_EMAIL")

# ---- Security ----
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 60 * 60
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

cloudinary.config(
    cloud_name='dxslozfwa',
    api_key='761268614366864',
    api_secret='0rEtaxo9thaaIB_ieP-GnsUMdII',
    secure=True
)

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': 'dxslozfwa',
    'API_KEY':'761268614366864',
    'API_SECRET': '0rEtaxo9thaaIB_ieP-GnsUMdII',
}
