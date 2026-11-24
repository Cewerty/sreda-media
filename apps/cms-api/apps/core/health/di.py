"""Dishka-провайдер проб (ADR 0011 §68–70, ADR 0015 §41)."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from apps.core.health.adapters import DatabaseProbe, DjangoReadinessProbe
from apps.core.health.ports import ReadinessProbe
from config.runtime import AppSettings


class HealthProvider(Provider):
    """Регистрирует `ReadinessProbe` в REQUEST-скопе."""

    @provide(scope=Scope.REQUEST, provides=ReadinessProbe)
    def provide_readiness_probe(self, settings: AppSettings) -> ReadinessProbe:
        """Собрать агрегатор проб без открытия соединений при создании."""
        timeout = settings.readiness_timeout_seconds
        return DjangoReadinessProbe(probes=[DatabaseProbe(timeout=timeout)], timeout=timeout)
