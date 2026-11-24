import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from config.runtime import AppSettings

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = {
    "DJANGO_ENV": "production",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": "synthetic-canary-key",
    "DJANGO_ALLOWED_HOSTS": "one.example, two.example",
    "RELEASE": "v0.2",
}


def test_dotenv_and_precedence(tmp_path, monkeypatch):
    for key in (*PRODUCTION, "LOG_LEVEL"):
        monkeypatch.delenv(key, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("DJANGO_SECRET_KEY=\nRELEASE=from-file\n", encoding="utf-8")
    assert AppSettings(_env_file=dotenv).release == "from-file"
    monkeypatch.setenv("RELEASE", "from-process")
    settings = AppSettings(_env_file=dotenv)
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
    ],
)
def test_invalid_production(field, value):
    with pytest.raises(ValidationError, match=field):
        AppSettings(_env_file=None, **(PRODUCTION | {field: value}))


@pytest.mark.parametrize("args", [["config_check.py"], ["manage.py", "check"]])
@pytest.mark.parametrize("invalid_field", [None, "DJANGO_DEBUG", "LOG_LEVEL"])
def test_entrypoint(args, invalid_field):
    env = os.environ | PRODUCTION
    if invalid_field is not None:
        env[invalid_field] = "invalid-canary-value"
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and test-owned arguments
        [sys.executable, *args], cwd=ROOT, env=env, capture_output=True, timeout=120, check=False
    )
    output = result.stdout + result.stderr
    assert (result.returncode == 0) == (invalid_field is None)
    if invalid_field is not None:
        assert invalid_field.encode() in output
    assert b"canary" not in output
