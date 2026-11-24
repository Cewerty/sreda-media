import os
import sys
from pathlib import Path

from dmr.settings import Settings

from .observability import django_logging
from .runtime import get_settings

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# settings.py лежит в backend/config/, поэтому BASE_DIR указывает на папку backend/
BASE_DIR = Path(__file__).resolve().parent.parent

# Добавляем корень backend в sys.path, чтобы корректно резолвились импорты "apps.*" и "config.*"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


_runtime = get_settings()
DEBUG = _runtime.debug
ALLOWED_HOSTS = list(_runtime.allowed_hosts)
SECRET_KEY = _runtime.secret_key.get_secret_value()
LOGGING = django_logging(_runtime.log_level)
del _runtime

# Application definition

INSTALLED_APPS = [
    # ASGI-сервер для runserver (async-вьюхи + async Dishka-контейнер)
    "daphne",
    # Модули доменной логики и ядра
    "apps.core",
    "apps.users",
    # Django-modern-rest (необходим для статики и шаблонов Swagger UI / OpenAPI)
    "dmr",
    # Стандартные приложения Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

# Dev-приложение для `manage.py lintmigrations` подключается только на полном
# прогоне quality_gate.py. В продовом образе его нет, поэтому settings не ломается.
if os.environ.get("DJANGO_QUALITY_GATE") == "1":
    INSTALLED_APPS.append("django_migration_linter")

MIDDLEWARE = [
    "config.http_logging.request_logging",
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise раздаёт статику из STATIC_ROOT под любым ASGI/WSGI-сервером
    # (uvicorn/daphne/gunicorn), а не только под runserver. Должен идти сразу после SecurityMiddleware.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # DMR автоматически освобождает API-контроллеры от CSRF
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Точки входа переведены на модуль config
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# Templates
# DMR использует встроенные шаблоны для рендера Swagger UI, поэтому APP_DIRS=True обязателен
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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


# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Custom User Model
# Для приложения 'apps.users' стандартным app_label остаётся 'users'
AUTH_USER_MODEL = "users.CustomUser"

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


# Internationalization
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

# STORAGES
# WhiteNoise-хранилище: раздаёт статику с gzip/brotli-сжатием и корректными кэш-заголовками.
# Используем CompressedStaticFilesStorage (без манифеста), чтобы collectstatic не падал
# на битых ссылках внутри сторонних бандлов (Swagger UI и т.п.).
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}


# Конфигурация DMR (глобальные настройки API). Ключи — Settings enum, не строки:
# dmr валидирует их при импорте, а config_check.py ловит тихое отключение.
DMR_SETTINGS = {
    # Строгая валидация исходящих ответов на соответствие объявленным типам и статус-кодам.
    Settings.validate_responses: True,
}


# Email
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
