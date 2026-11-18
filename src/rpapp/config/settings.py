import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "django-insecure-change-this-before-deployment"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "127.0.0.1"
    ).split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rpapp.todos",
    "sslserver",
    "mozilla_django_oidc",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "rpapp.todos.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "rpapp.config.urls"
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
    },
]
WSGI_APPLICATION = "rpapp.config.wsgi.application"
ASGI_APPLICATION = "rpapp.config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
    }
}

AUTHENTICATION_BACKENDS = [
    "rpapp.todos.authentication.GluuOIDCAuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "/oidc/authenticate/"
LOGIN_REDIRECT_URL = "/todos/"
LOGOUT_REDIRECT_URL = "/"

OIDC_OP_LOGOUT_ENDPOINT = os.environ.get("GLUU_OIDC_END_SESSION_ENDPOINT", "")
OIDC_OP_LOGOUT_URL_METHOD = "rpapp.todos.oidc.build_logout_url"
OIDC_STORE_ID_TOKEN = True

OIDC_RP_CLIENT_ID = os.environ.get("GLUU_OIDC_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.environ.get("GLUU_OIDC_CLIENT_SECRET", "")
OIDC_RP_SIGN_ALGO = os.environ.get("GLUU_OIDC_SIGN_ALGO", "RS256")
OIDC_OP_ISSUER = os.environ.get("GLUU_OIDC_ISSUER", "")
OIDC_OP_AUTHORIZATION_ENDPOINT = os.environ.get("GLUU_OIDC_AUTHORIZATION_ENDPOINT", "")
OIDC_OP_TOKEN_ENDPOINT = os.environ.get("GLUU_OIDC_TOKEN_ENDPOINT", "")
OIDC_OP_USER_ENDPOINT = os.environ.get("GLUU_OIDC_USERINFO_ENDPOINT", "")
OIDC_OP_JWKS_ENDPOINT = os.environ.get("GLUU_OIDC_JWKS_ENDPOINT", "")
OIDC_RP_SCOPES = "openid email profile view_profile"
OIDC_TOKEN_USE_BASIC_AUTH = True
OIDC_VERIFY_SSL = True if os.environ.get("GLUU_OIDC_VERIFY_SSL", "true").lower() == "true" else False
OIDC_USE_NONCE = True
OIDC_CREATE_USER = True

SCIM_BASE_URL = os.environ.get("GLUU_SCIM_BASE_URL", "").rstrip("/")
SCIM_CLIENT_ID = os.environ.get("GLUU_SCIM_CLIENT_ID", "")
SCIM_CLIENT_SECRET = os.environ.get("GLUU_SCIM_CLIENT_SECRET", "")
SCIM_SCOPE = os.environ.get(
    "GLUU_SCIM_SCOPE",
    "https://gluu.org/scim/users.read https://gluu.org/scim/users.write",
)
SCIM_TOKEN_AUTH_METHOD = os.environ.get(
    "GLUU_SCIM_TOKEN_AUTH_METHOD", "client_secret_basic"
)
SCIM_TIMEOUT_SECONDS = float(os.environ.get("GLUU_SCIM_TIMEOUT_SECONDS", "10"))
SCIM_VERIFY_SSL = os.environ.get("GLUU_SCIM_VERIFY_SSL", "false").lower() == "true"

LANGUAGE_CODE = "ja"
TIME_ZONE = "Asia/Tokyo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
        },
    },
    "loggers": {
        "rpapp.todos.authentication": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rpapp.todos.scim": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
