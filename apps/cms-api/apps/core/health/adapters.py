"""Адаптеры проверки зависимостей (ADR 0011 §68, ADR 0015 §4/§41).

Соединение открывается **лениво внутри вызова**, а не при импорте или в
APP-scope: ADR 0015 §41 запрещает feature-модулю открывать БД на импорте.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Final, Literal

from asgiref.sync import sync_to_async
from django.db import connections

from apps.core.health.ports import DependencyProbe
from apps.core.health.schemas import ReadinessCheck

#: Бюджет по умолчанию. Таймаут уровня драйвера (`connect_timeout`,
#: `statement_timeout`) и это значение должны прийти из typed config в #41
#: (issue OPEN): `AppSettings` из PR #42 пока не содержит полей БД.
#: См. Q2 спецификации.
DEFAULT_TIMEOUT_SECONDS: Final[float] = 1.0


class DatabaseProbe:
    """Проверка доступности основной БД через `SELECT 1`."""

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Запомнить бюджет проверки, не открывая соединение."""
        self._timeout = timeout

    @property
    def name(self) -> Literal["database", "storage"]:
        """Вернуть стабильное имя зависимости для ответа."""
        return "database"

    async def check(self) -> ReadinessCheck:
        """Проверить БД и вернуть только безопасную категорию результата."""
        try:
            await asyncio.wait_for(
                sync_to_async(self._ping, thread_sensitive=False)(),
                timeout=self._timeout,
            )
        except Exception:
            # Readiness не должен раскрывать raw exception, DSN или путь.
            # Исключение намеренно не логируется здесь: контракт событий — #27.
            return ReadinessCheck(name=self.name, status="unavailable")
        else:
            return ReadinessCheck(name=self.name, status="ok")

    def _ping(self) -> None:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()


class DjangoReadinessProbe:
    """Агрегатор всех используемых зависимостей для `/readyz`.

    В 0.2 подключена только БД: media storage появляется в 0.4 (EDIT-02,
    NFR-OPS-02), а ADR 0015 §69 требует проверки «используемого» хранилища.
    `StorageProbe` добавляется в список без правки контроллера и ADR.
    """

    def __init__(
        self,
        probes: Sequence[DependencyProbe],
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Запомнить проверки и общий бюджет, не выполняя их."""
        self._probes = probes
        self._timeout = timeout

    async def check(self) -> list[ReadinessCheck]:
        """Опросить зависимости параллельно в пределах общего бюджета."""
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*(probe.check() for probe in self._probes)),
                timeout=self._timeout,
            )
        except Exception:
            return [ReadinessCheck(name=probe.name, status="unavailable") for probe in self._probes]
        else:
            return list(results)
