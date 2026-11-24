"""Порты проверки готовности (ADR 0011 §68, ADR 0015 §4).

Контроллер зависит от абстракции, а не от Django ORM: это позволяет в тестах
подменить именно зависимость, а не саму проверяемую логику (#26).
"""

from __future__ import annotations

from typing import Literal, Protocol

from apps.core.health.schemas import ReadinessCheck


class DependencyProbe(Protocol):
    """Проверка одной используемой зависимости."""

    @property
    def name(self) -> Literal["database", "storage"]:
        """Имя зависимости для безопасного поля `ReadinessCheck.name`."""
        ...

    async def check(self) -> ReadinessCheck:
        """Вернуть результат проверки, не раскрывая деталей отказа."""
        ...


class ReadinessProbe(Protocol):
    """Агрегатор всех используемых проверок для `/readyz`."""

    async def check(self) -> list[ReadinessCheck]:
        """Вернуть результаты по всем подключённым зависимостям."""
        ...
