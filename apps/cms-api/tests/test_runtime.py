import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.runtime import AppSettings

ROOT = Path(__file__).resolve().parents[1]
DEV_ENV = ROOT / ".env.example"
PRODUCTION = {
    "DJANGO_ENV": "production",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "synthetic-canary-key-" + "abcdef0123456789" * 3,
    "DJANGO_ALLOWED_HOSTS": "one.example, two.example",
    "RELEASE": "v0.2",
    "POSTGRES_HOST": "db.example",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "application",
    "POSTGRES_USER": "application",
    "POSTGRES_PASSWORD": "synthetic-db-password",
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example",
    "EMAIL_PORT": "587",
    "DEFAULT_FROM_EMAIL": "cms@example.org",
}


def test_dotenv_and_precedence(tmp_path, monkeypatch):
    for key in (*PRODUCTION, "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("RELEASE=from-file\n", encoding="utf-8")
    assert AppSettings(_env_file=(DEV_ENV, dotenv)).release == "from-file"
    monkeypatch.setenv("RELEASE", "from-process")
    settings = AppSettings(_env_file=(DEV_ENV, dotenv))
    assert settings.release == "from-process"
    assert settings.secret_key.get_secret_value().startswith("django-insecure-")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("DJANGO_SECRET_KEY", ""),
        ("DJANGO_SECRET_KEY", "django-insecure-test"),
        ("DJANGO_DEBUG", "true"),
        ("DJANGO_ALLOWED_HOSTS", "host,*"),
        ("DJANGO_ALLOWED_HOSTS", ""),
        ("RELEASE", "  "),
        ("POSTGRES_PASSWORD", "  "),
        ("POSTGRES_HOST", " "),
        ("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"),
        ("EMAIL_BACKEND", "does_not_exist.EmailBackend"),
    ],
)
def test_invalid_production(field, value):
    with pytest.raises(ValidationError, match=field):
        AppSettings(_env_file=None, **(PRODUCTION | {field: value}))


@pytest.mark.parametrize("field", sorted(PRODUCTION))
def test_missing_production_parameter(field, monkeypatch):
    monkeypatch.delenv(field, raising=False)
    with pytest.raises(ValidationError, match=field):
        AppSettings(_env_file=None, **{name: value for name, value in PRODUCTION.items() if name != field})


@pytest.mark.parametrize("profile", ["dev", "production"])
@pytest.mark.parametrize("flag", ["DMR_VALIDATE_RESPONSES", "DMR_SEMANTIC_RESPONSES"])
def test_cannot_disable_dmr_validation(profile, flag):
    with pytest.raises(ValidationError, match=flag):
        AppSettings(_env_file=None, **(PRODUCTION | {"DJANGO_ENV": profile, flag: "0"}))


@pytest.mark.parametrize("field", ["DMR_PARSERS", "DMR_RENDERERS"])
def test_dmr_requires_nonempty_codecs(field):
    with pytest.raises(ValidationError, match=field):
        AppSettings(_env_file=None, **(PRODUCTION | {field: ()}))


@pytest.mark.parametrize("invalid_field", [None, "DJANGO_DEBUG", "LOG_LEVEL", "POSTGRES_PASSWORD"])
def test_entrypoint(invalid_field):
    env = os.environ | PRODUCTION
    if invalid_field == "POSTGRES_PASSWORD":
        del env[invalid_field]
    elif invalid_field is not None:
        env[invalid_field] = "invalid-canary-value"
    result = subprocess.run(
        [sys.executable, "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    assert (result.returncode == 0) == (invalid_field is None)
    if invalid_field is not None:
        assert invalid_field.encode() in output
    assert b"canary" not in output
    assert b"synthetic-db-password" not in output
