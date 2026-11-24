# Тесты `cms-api`

Инструменты (`pytest`, `pytest-django`, `pytest-cov`, `pytest-xdist`,
`polyfactory`, `schemathesis`, `django-test-migrations`) уже объявлены в
dev-группе `pyproject.toml`. Тесты конфигурации и логирования запускает `just tests`.
Этот рецепт входит в `just check`.

Конвенции тестов CMS

- pytest-стиль вместо `django.test.TestCase`;
- `dmr_rf` (`DMRRequestFactory`) — unit-тесты контроллеров без роутинга,
  `dmr_client` (`DMRClient`) — полный цикл; для async — `DMRAsync*`;
- `polyfactory` генерирует payload из DTO (`__check_model__ = True`);
- `schemathesis` — property-based проверки против OpenAPI-схемы;
- приоритет по ADR 0004 §2 и ADR 0012: переходы статусов, object-level права,
  rollback без уведомления. Процент покрытия не самоцель.
