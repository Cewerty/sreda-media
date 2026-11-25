"""Тесты AC-1…AC-6, AC-8 спецификации `ops-04-health-readiness`.

Подменяется только **зависимость** (БД/таймаут), а не проверяемая логика:
#26 требует «не подменять тесты заглушками».

Используется `dmr_async_client` + `anyio`: контейнер проекта собран через
`make_async_container`, поэтому sync-ветка `dmr_dishka.container_middleware`
несовместима с синхронным тест-клиентом (это общая находка для #26).
"""

from __future__ import annotations

import time
from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.db.backends.base.base import BaseDatabaseWrapper

from apps.core.health.adapters import DatabaseProbe
from config import urls
from config.runtime import get_settings

pytestmark = pytest.mark.anyio


async def test_ac1_healthz_alive_without_db(dmr_async_client, db):
    """AC-1: liveness не открывает курсор БД и не требует авторизации.

    `django_assert_num_queries` синхронный и несовместим с async-тестом,
    поэтому инструментируем `cursor()` и считаем вызовы (без заглушек).
    """
    calls: list[str] = []
    original = BaseDatabaseWrapper.cursor

    def _counting(self, *args, **kwargs):
        calls.append(self.alias)
        return original(self, *args, **kwargs)

    with patch.object(BaseDatabaseWrapper, "cursor", _counting):
        response = await dmr_async_client.get("/healthz")

    assert calls == []
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"status": "ok"}
    body = response.content.decode()
    assert "Traceback" not in body
    assert "dsn" not in body.lower()


async def test_ac2_readyz_ok(dmr_async_client, db):
    """AC-2: при доступной БД readiness зелёная."""
    response = await dmr_async_client.get("/readyz")

    assert response.status_code == HTTPStatus.OK
    assert response.json() == {
        "status": "ok",
        "checks": [{"name": "database", "status": "ok"}],
    }


async def test_ac3_readyz_db_failure(dmr_async_client, db, monkeypatch):
    """AC-3/AC-5: отказ БД даёт healthz=200, readyz=503 без утечки деталей."""

    def _fail(self):
        raise OperationalError("simulated outage at secret-host:5432/secret-db")

    monkeypatch.setattr(DatabaseProbe, "_ping", _fail)

    health = await dmr_async_client.get("/healthz")
    ready = await dmr_async_client.get("/readyz")

    assert health.status_code == HTTPStatus.OK
    assert ready.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    body = ready.content.decode()
    assert "simulated outage" not in body
    assert "secret-host" not in body
    assert "secret-db" not in body
    assert "Traceback" not in body


async def test_ac4_readyz_timeout(dmr_async_client, db, monkeypatch):
    """AC-4: зависшая зависимость не превращается в зависший запрос."""
    monkeypatch.setitem(vars(get_settings()), "readiness_timeout_seconds", 0.01)

    def _slow(self):
        time.sleep(0.5)

    monkeypatch.setattr(DatabaseProbe, "_ping", _slow)

    response = await dmr_async_client.get("/readyz")

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE


async def test_ac6_probes_are_anonymous(dmr_async_client, db):
    """AC-6: пробы доступны без сессии, cookie и CSRF-токена."""
    for url in ("/healthz", "/readyz"):
        response = await dmr_async_client.get(url)
        assert response.status_code == HTTPStatus.OK


def test_ac8_probes_absent_from_openapi():
    """AC-8: пробы не попадают в OpenAPI и не меняют контракт ADR 0014."""
    paths = urls.schema.convert()["paths"]

    assert "/healthz" not in paths
    assert "/readyz" not in paths
    assert "/api/v1/users/" in paths
