"""Dishka-провайдер проб (ADR 0011 §68–70, ADR 0015 §41)."""

from __future__ import annotations

from typing import Final

from dishka import Provider, Scope, provide

from apps.core.health.adapters import DatabaseProbe, DjangoReadinessProbe
from apps.core.health.ports import ReadinessProbe

#: Общий бюджет проверки. Читается при создании пробы, чтобы тесты могли
#: задать короткий таймаут, а #26 — подставить значение из typed config.
READINESS_TIMEOUT_SECONDS: Final[float] = 1.0


class HealthProvider(Provider):
    """Регистрирует `ReadinessProbe` в REQUEST-скопе."""

    @provide(scope=Scope.REQUEST, provides=ReadinessProbe)
    def provide_readiness_probe(self) -> ReadinessProbe:
        """Собрать агрегатор проб без открытия соединений при создании."""
        return DjangoReadinessProbe(
            probes=[DatabaseProbe(timeout=READINESS_TIMEOUT_SECONDS)],
            timeout=READINESS_TIMEOUT_SECONDS,
        )
