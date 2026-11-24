from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from django.core.exceptions import ImproperlyConfigured
from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEV_KEY = "django-insecure-7^&7z)1wzsk$4!=650b(u+o%_$8jb$%li%0^0bcdegp!vwkm1q"


class AppSettings(BaseSettings):
    """Параметры процесса CMS, проверяемые до запуска приложения."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    environment: Literal["dev", "production"] = Field(default="dev", validation_alias="DJANGO_ENV")
    debug: bool = Field(default=True, validation_alias="DJANGO_DEBUG")
    secret_key: SecretStr = Field(default=SecretStr(_DEV_KEY), validation_alias="DJANGO_SECRET_KEY")
    allowed_hosts: Annotated[tuple[str, ...], NoDecode] = Field(default=("*",), validation_alias="DJANGO_ALLOWED_HOSTS")
    release: str = Field(default="", validation_alias="RELEASE")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_hosts(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(host.strip() for host in value.split(",") if host.strip())
        return value

    @field_validator("secret_key", mode="before")
    @classmethod
    def local_key(cls, value: object) -> object:
        return _DEV_KEY if value == "" else value

    @model_validator(mode="after")
    def validate_production(self) -> Self:
        if self.environment != "production":
            return self
        if self.debug:
            raise ValueError("DJANGO_DEBUG должен быть выключен в production")
        key = self.secret_key.get_secret_value().strip()
        if not key or key.startswith("django-insecure-"):
            raise ValueError("DJANGO_SECRET_KEY требует собственного секрета в production")
        if not self.allowed_hosts or any("*" in host for host in self.allowed_hosts):
            raise ValueError("DJANGO_ALLOWED_HOSTS требует явных хостов без wildcard")
        if not self.release.strip():
            raise ValueError("RELEASE требует идентификатора релиза в production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    try:
        return AppSettings()
    except ValidationError as exc:
        rules = []
        for error in exc.errors(include_input=False, include_url=False):
            name = ".".join(map(str, error["loc"]))
            rules.append(f"{name}: {error['msg']}" if name else error["msg"])
        raise ImproperlyConfigured("\n".join(rules)) from None
