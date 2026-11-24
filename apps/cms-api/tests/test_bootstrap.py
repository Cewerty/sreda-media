import subprocess
import sys
from pathlib import Path


def test_asgi_bootstrap():
    script = """
import asyncio
from unittest.mock import patch
import dishka
from config.runtime import AppSettings, get_settings
from structlog.stdlib import BoundLogger

with patch.object(dishka, 'make_async_container', wraps=dishka.make_async_container) as build:
    from config.asgi import application
    from config.wsgi import application as wsgi
    from django.conf import settings
    assert build.call_count == 1

async def verify():
    container = settings.__DISHKA_CONTAINER__
    assert await container.get(AppSettings) is get_settings()
    assert await container.get(BoundLogger) is await container.get(BoundLogger)
asyncio.run(verify())
"""
    subprocess.run(  # noqa: S603 -- fixed interpreter and test-owned arguments
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1], timeout=120, check=True
    )
