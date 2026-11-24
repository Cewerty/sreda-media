"""Типизированные ответы health/readiness.

Тела намеренно минимальны: ADR 0015 §69 запрещает раскрывать DSN, пути и raw
exception, NFR-SEC-03 — секреты, ADR 0005 §37 — stack trace и персональные данные.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Ответ liveness: живой Django HTTP-процесс."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"


class ReadinessCheck(BaseModel):
    """Результат проверки одной используемой зависимости."""

    model_config = ConfigDict(frozen=True)

    name: Literal["database", "storage"]
    status: Literal["ok", "unavailable"]


class ReadyResponse(BaseModel):
    """Ответ readiness: все используемые зависимости доступны."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    checks: list[ReadinessCheck]
