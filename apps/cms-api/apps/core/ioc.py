from dishka import Provider, Scope, from_context, provide
from structlog.stdlib import BoundLogger

from apps.users.services import UserService
from config.runtime import AppSettings


class AppProvider(Provider):
    settings = from_context(provides=AppSettings, scope=Scope.APP)
    logger = from_context(provides=BoundLogger, scope=Scope.APP)

    @provide(scope=Scope.REQUEST)
    def provide_user_service(self) -> UserService:
        return UserService()
