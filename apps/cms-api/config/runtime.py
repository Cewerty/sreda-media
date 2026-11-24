"""Typed config `cms-api` (ADR 0015 §2, #41)."""

from __future__ import annotations

import os
from functools import lru_cache
from inspect import isclass
from pathlib import Path
from typing import Annotated, Literal, Self

from django.core.checks.security.base import (
    SECRET_KEY_INSECURE_PREFIX,
    SECRET_KEY_MIN_LENGTH,
    SECRET_KEY_MIN_UNIQUE_CHARACTERS,
)
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.smtp import EmailBackend
from django.utils.module_loading import import_string
from dmr.parsers import Parser
from dmr.renderers import Renderer
from dmr.settings import default_parser, default_renderer
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class AppSettings(BaseSettings):
    """Параметры процесса CMS, проверяемые до запуска приложения."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        frozen=True,
        hide_input_in_errors=True,
        arbitrary_types_allowed=True,
    )

    # --- Общие (#42) ---
    environment: Literal["dev", "production"] = Field(validation_alias="DJANGO_ENV")
    debug: bool = Field(validation_alias="DJANGO_DEBUG")
    secret_key: SecretStr = Field(validation_alias="DJANGO_SECRET_KEY")
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = Field(validation_alias="DJANGO_ALLOWED_HOSTS", min_length=1)
    release: str = Field(default="", validation_alias="RELEASE")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    #: Часовой пояс БД/приложения. Вынесен в конфиг, чтобы окружение без tzdata
    #: (например, локальный pgserver) могло задать GMT, не меняя код.
    time_zone: str = Field(default="UTC", validation_alias="DJANGO_TIME_ZONE")

    # --- PostgreSQL (#41): только он, без SQLite-fallback ---
    postgres_host: str = Field(validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(validation_alias="POSTGRES_PORT", ge=1, le=65535)
    postgres_db: str = Field(validation_alias="POSTGRES_DB")
    postgres_user: str = Field(validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(validation_alias="POSTGRES_PASSWORD")
    #: libpq `connect_timeout`, секунды.
    connect_timeout: int = Field(default=5, validation_alias="POSTGRES_CONNECT_TIMEOUT", ge=1)
    #: `-c statement_timeout=<ms>`, миллисекунды. 0 — без ограничения.
    statement_timeout: int = Field(default=3000, validation_alias="POSTGRES_STATEMENT_TIMEOUT", ge=0)
    #: Общий бюджет `asyncio.wait_for` для readiness-проб (#28, Q2).
    readiness_timeout_seconds: float = Field(default=1.0, validation_alias="READINESS_TIMEOUT_SECONDS", gt=0)

    # --- Почта: prod-бэкенд, иначе check --deploy даёт mail.E001 ---
    email_backend: str = Field(validation_alias="EMAIL_BACKEND")
    email_host: str = Field(validation_alias="EMAIL_HOST")
    email_port: int = Field(validation_alias="EMAIL_PORT", ge=1, le=65535)
    email_host_user: str = Field(default="", validation_alias="EMAIL_HOST_USER")
    email_host_password: SecretStr = Field(default=SecretStr(""), validation_alias="EMAIL_HOST_PASSWORD")
    email_use_tls: bool = Field(default=False, validation_alias="EMAIL_USE_TLS")
    email_timeout: int = Field(default=10, validation_alias="EMAIL_TIMEOUT", ge=1)
    default_from_email: str = Field(validation_alias="DEFAULT_FROM_EMAIL")

    # --- DMR: защита от тихого отключения валидации (#41, Q4) ---
    dmr_validate_responses: bool = Field(default=True, validation_alias="DMR_VALIDATE_RESPONSES")
    dmr_semantic_responses: bool = Field(default=True, validation_alias="DMR_SEMANTIC_RESPONSES")
    dmr_parsers: tuple[Parser, ...] = Field(default=(default_parser,), min_length=1, validation_alias="DMR_PARSERS")
    dmr_renderers: tuple[Renderer, ...] = Field(
        default=(default_renderer,), min_length=1, validation_alias="DMR_RENDERERS"
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_hosts(cls, value: object) -> object:
        """`DJANGO_ALLOWED_HOSTS` приходит строкой через запятую."""
        if isinstance(value, str):
            return tuple(host.strip() for host in value.split(",") if host.strip())
        return value

    @field_validator("secret_key", "postgres_password")
    @classmethod
    def require_secret(cls, value: SecretStr) -> SecretStr:
        """Проверить заполненность секрета до старта приложения."""
        if not value.get_secret_value().strip():
            raise ValueError("требуется непустое значение")
        return value

    @field_validator("postgres_host", "postgres_db", "postgres_user", "email_host", "default_from_email")
    @classmethod
    def require_text(cls, value: str) -> str:
        """Проверить заполненность обязательных параметров."""
        if not value.strip():
            raise ValueError("требуется непустое значение")
        return value

    @field_validator("dmr_validate_responses", "dmr_semantic_responses")
    @classmethod
    def require_dmr_validation(cls, value: bool) -> bool:
        """Сохранить обязательные гарантии DMR во всех профилях."""
        if not value:
            raise ValueError("отключение запрещено")
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        """Fail-fast: prod не стартует с dev-значениями (ADR 0015 §2)."""
        if self.environment == "production":
            self._validate_prod_security()
            self._validate_prod_services()
        return self

    def _validate_prod_security(self) -> None:
        """DEBUG, секрет, хосты и релиз — без dev-значений."""
        if self.debug:
            raise ValueError("DJANGO_DEBUG должен быть выключен в production")
        key = self.secret_key.get_secret_value().strip()
        if (
            key.startswith(SECRET_KEY_INSECURE_PREFIX)
            or len(key) < SECRET_KEY_MIN_LENGTH
            or len(set(key)) < SECRET_KEY_MIN_UNIQUE_CHARACTERS
        ):
            raise ValueError("DJANGO_SECRET_KEY требует стойкого секрета в production")
        if any("*" in host for host in self.allowed_hosts):
            raise ValueError("DJANGO_ALLOWED_HOSTS требует явных хостов без wildcard")
        if not self.release.strip():
            raise ValueError("RELEASE требует идентификатора релиза в production")

    def _validate_prod_services(self) -> None:
        """Проверить, что production использует существующий SMTP-бэкенд."""
        try:
            backend = import_string(self.email_backend)
        except ImportError:
            raise ValueError("EMAIL_BACKEND требует импортируемого SMTP-бэкенда в production") from None
        if not isclass(backend) or not issubclass(backend, EmailBackend):
            raise ValueError("EMAIL_BACKEND требует SMTP-бэкенда в production")


@lru_cache(maxsize=1)
def _load_settings() -> AppSettings:
    """Один раз собрать и проверить конфигурацию на bootstrap."""
    env_file = None if os.environ.get("DJANGO_ENV") == "production" else _ENV_FILE
    # Pyright sees required model fields but BaseSettings populates them from its sources.
    return AppSettings(_env_file=env_file)  # pyright: ignore[reportCallIssue]


def get_settings() -> AppSettings:
    """Вернуть проверенные настройки, не раскрывая значения секретов в ошибке."""
    try:
        return _load_settings()
    except ValidationError as exc:
        rules: list[str] = []
        for error in exc.errors(include_input=False, include_url=False):
            name = ".".join(map(str, error["loc"]))
            rules.append(f"{name}: {error['msg']}" if name else error["msg"])
        raise ImproperlyConfigured("\n".join(rules)) from None
