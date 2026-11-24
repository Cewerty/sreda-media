from collections.abc import Callable

import structlog
from dishka import make_async_container
from django.apps import AppConfig
from django.conf import settings as django_settings
from django.utils.decorators import async_only_middleware
from dmr_dishka import container_middleware, setup_dishka
from structlog.stdlib import BoundLogger

from config.http_logging import RequestLog
from config.observability import configure_logging
from config.runtime import AppSettings, get_settings


# DMR selects its sync context manager under WSGI unless Django adapts
# the middleware to the AsyncContainer created below.
@async_only_middleware
def async_container_middleware(get_response: Callable) -> Callable:
    return container_middleware(get_response)


class CoreConfig(AppConfig):
    """Конфигурация ядрового приложения и его DI-контейнера."""

    name = "apps.core"

    def ready(self) -> None:
        """Собрать Dishka-контейнер и подключить его к DMR."""
        # Импорт внутри ready(): на уровне модуля models ещё недоступны.
        from apps.core.health.di import HealthProvider  # noqa: PLC0415
        from apps.core.ioc import AppProvider  # noqa: PLC0415

        if hasattr(self, "request_log"):
            return
        settings = get_settings()
        logger = configure_logging(settings)
        http_logger = structlog.stdlib.get_logger("cms.http").bind(**structlog.get_context(logger))
        self.request_log = RequestLog(http_logger)
        container = make_async_container(
            AppProvider(),
            HealthProvider(),
            context={AppSettings: settings, BoundLogger: logger},
        )
        setup_dishka(container)
        index = django_settings.MIDDLEWARE.index("dmr_dishka.container.container_middleware")
        django_settings.MIDDLEWARE[index] = "apps.core.apps.async_container_middleware"
