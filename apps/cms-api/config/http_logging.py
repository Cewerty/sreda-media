from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http import HTTPStatus
from inspect import iscoroutinefunction
from time import perf_counter
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from django.apps import apps
from django.http import HttpRequest, HttpResponse
from django.utils.decorators import sync_and_async_middleware
from structlog.contextvars import bound_contextvars, get_contextvars
from structlog.stdlib import BoundLogger

if TYPE_CHECKING:
    from apps.core.apps import CoreConfig


class RequestLog:
    """Record an HTTP completion using the process logger and request-local context."""

    def __init__(self, logger: BoundLogger) -> None:
        self.logger = logger

    @contextmanager
    def start(self) -> Iterator[float]:
        """Bind a fresh ID until the response has been logged."""
        with bound_contextvars(correlation_id=str(uuid4())):
            yield perf_counter()

    def finish(self, response: HttpResponse, started: float) -> HttpResponse:
        """Emit only the fields specified in ADR 0005."""
        status = response.status_code
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            outcome = "server_error"
        elif status >= HTTPStatus.BAD_REQUEST:
            outcome = "client_error"
        else:
            outcome = "success"
        response["X-Correlation-ID"] = get_contextvars()["correlation_id"]
        self.logger.info(
            "request_finished",
            operation="http_request",
            outcome=outcome,
            status_code=status,
            elapsed_ms=round((perf_counter() - started) * 1000, 3),
        )
        return response


@sync_and_async_middleware
def request_logging(get_response: Callable) -> Callable:
    recorder = cast("CoreConfig", apps.get_app_config("core")).request_log
    if iscoroutinefunction(get_response):

        async def async_middleware(request: HttpRequest) -> HttpResponse:
            with recorder.start() as started:
                return recorder.finish(await get_response(request), started)

        return async_middleware

    def middleware(request: HttpRequest) -> HttpResponse:
        with recorder.start() as started:
            return recorder.finish(get_response(request), started)

    return middleware
