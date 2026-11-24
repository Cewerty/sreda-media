"""Preflight конфигурации cms-api (ADR 0015 §2, NFR-SEC-03).

Запуск: `uv run python config_check.py` из `apps/cms-api`.
Сообщает имя параметра и правило, никогда не печатает значения секретов.
Не требует django.setup(): читает модуль settings напрямую.
"""

from __future__ import annotations

from importlib import import_module

from django.core.exceptions import ImproperlyConfigured
from dmr.settings import Settings


def main() -> int:
    """Проверить настройки DMR и prod-окружение."""
    errors: list[str] = []
    try:
        dmr_settings = import_module("config.settings").DMR_SETTINGS
    except ImproperlyConfigured as exc:
        print(f"config-check: {exc}")
        return 1

    # Документация DMR: ключи DMR_SETTINGS типизированы Settings enum и
    # валидируются при импорте. Строковый ключ — тихое расхождение.
    for key in dmr_settings:
        if not isinstance(key, Settings):
            errors.append("DMR_SETTINGS: ключ не является Settings enum")

    # Главная защита от «тихого отключения»: в dev/test валидация включена.
    if dmr_settings.get(Settings.validate_responses) is not True:
        errors.append("DMR_SETTINGS: validate_responses должен быть True в dev/test")

    if dmr_settings.get(Settings.semantic_responses) is False:
        errors.append("DMR_SETTINGS: semantic_responses отключать нельзя")

    for name in ("parsers", "renderers"):
        member = getattr(Settings, name, None)
        value = dmr_settings.get(member) if member is not None else None
        if isinstance(value, (list, tuple)) and not value:
            errors.append(f"DMR_SETTINGS: {name} не должен быть пустым")

    if errors:
        for line in errors:
            print(f"config-check: {line}")
        return 1
    print("config-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
