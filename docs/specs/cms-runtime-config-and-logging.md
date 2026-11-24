# Конфигурация и HTTP-логи CMS

**Версия** 0.2 · **Статус** черновик · **Владелец** Илья

Основание — [PRD](../prd.md), NFR-OPS-01, NFR-SEC-03, [ADR 0005](../adr/0005-observability-glitchtip.md), [ADR 0011](../adr/0011-application-architecture-and-boundaries.md), [ADR 0015](../adr/0015-runtime-and-data-operations.md), [задача #27](https://github.com/Sreda-Media/sreda-media/issues/27).

## Результат и границы

Разработчик находит событие завершения HTTP-запроса по заголовку ответа `X-Correlation-ID`. Оператор проверяет production-конфигурацию перед запуском теми же правилами, что применяет Django. Поставка охватывает процесс CMS и его stdout.

## Поведение и ограничения

CMS загружает типизированные настройки при запуске. Переменные процесса имеют приоритет над локальным файлом `apps/cms-api/.env`. Production требует собственного секрета, выключенного debug, списка разрешённых хостов без wildcard и идентификатора релиза. Ошибка называет параметр и правило. Пример локальной конфигурации хранится в [.env.example](../../apps/cms-api/.env.example).

CMS генерирует UUID для каждого запроса независимо от заголовков клиента. Событие `request_finished` содержит UTC timestamp, component=cms-api, operation=http_request, environment, release, correlation_id, status_code и elapsed_ms. Для 2xx–3xx outcome равен success, для 4xx — client_error, для 5xx — server_error. Одна строка stdout соответствует одному JSON-событию. Данные запроса и текст исключений исключены из HTTP-логов.

При локальном запросе к `/docs/openapi.json/` CMS вернула заголовок
`X-Correlation-ID: e8412371-ffff-47b9-b144-b970fe7160bd` и записала в stdout

```json
{"component": "cms-api", "environment": "dev", "release": "local", "operation": "http_request", "outcome": "success", "status_code": 200, "elapsed_ms": 1671.26, "event": "request_finished", "correlation_id": "e8412371-ffff-47b9-b144-b970fe7160bd", "timestamp": "2026-11-24T08:36:54.996006Z"}
```

## Критерии приёмки

| ID | Исходные условия и действие | Ожидаемый результат | Как проверить |
| --- | --- | --- | --- |
| AC-1 | Запустить preflight и Django с валидным и ошибочным production env | Одинаковые правила при запуске и preflight, безопасная диагностика | Тесты запуска отдельного процесса |
| AC-2 | Получить 200, 404 и 500 | По одной JSON-записи с UUID из заголовка и соответствующим outcome | HTTP-тесты и захват stdout |
| AC-3 | Выполнить два параллельных запроса с внешним UUID и контрольным секретом | Разные UUID, контекст изолирован, секрет отсутствует в выводе | ASGI-тест и проверка stdout/stderr |
| AC-4 | Запустить ASGI и получить настройки и логгер из Dishka | Один контейнер и переиспользуемые зависимости APP | Тест bootstrap |
