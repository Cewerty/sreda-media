"""Транспорт health/readiness (NFR-OPS-04, ADR 0006 §1, ADR 0015 §4).

Пробы анонимны: `auth` и `throttling` не задаются, `Controller.as_view()`
снимает CSRF и `login_required` по умолчанию, GET не проверяется
`CsrfViewMiddleware`. Пути монтируются в корне, вне `api_v1_router` и OpenAPI.
"""

from __future__ import annotations

from http import HTTPStatus

from dmr import APIError, Controller, ResponseSpec, modify
from dmr.plugins.pydantic import PydanticFastSerializer
from dmr_dishka import FromDishka, inject

from apps.core.health.ports import ReadinessProbe
from apps.core.health.schemas import HealthResponse, ReadyResponse

# 503 объявлен явно: иначе включённый validate_responses завернёт ответ.
# См. $dmr -> references/validation.md.
_NOT_READY_SPEC: ResponseSpec = ResponseSpec(
    Controller.error_model,
    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
)


class HealthController(Controller[PydanticFastSerializer]):
    """Liveness: живой Django HTTP-процесс без обращений к зависимостям."""

    async def get(self) -> HealthResponse:
        """Вернуть признак живого процесса; не трогает БД и внешние API."""
        return HealthResponse()


class ReadyController(Controller[PydanticFastSerializer]):
    """Readiness: доступность используемых зависимостей."""

    @modify(extra_responses=[_NOT_READY_SPEC])
    @inject
    async def get(self, probe: FromDishka[ReadinessProbe]) -> ReadyResponse:
        """Вернуть 200 при готовности и 503 при отказе зависимости."""
        checks = await probe.check()
        if any(check.status != "ok" for check in checks):
            raise APIError(
                self.format_error("Service not ready"),
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        return ReadyResponse(checks=checks)
