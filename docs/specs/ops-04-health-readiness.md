# Health / readiness пробы CMS

**Версия:** 0.2 · **Статус:** согласована · **Владелец:** Илья (бэкенд); согласование эксплуатации — Костян

**Основание:** [PRD](../prd.md), NFR-OPS-04. Применимые решения: ADR 0005 (наблюдаемость), ADR 0006 (пути и Caddy), ADR 0011 (DI/границы), ADR 0013 (Proposed, фоновые процессы), ADR 0015 §2/§4 (конфигурация, liveness/readiness). Задача — issue #28, эпик #14 §2.2.

## Результат и границы

`cms-api` отдаёт две пробы с **разной семантикой**:

| | `/healthz` | `/readyz` |
| --- | --- | --- |
| Что показывает | жив Django HTTP-процесс | доступны используемые зависимости |
| Проверки | никаких: без БД, внешних API, DI и сетевых вызовов | БД; media storage — с 0.4 |
| Успех | 200 | 200 |
| Отказ | — | 503 |
| Таймаут | — | ограниченный, общий бюджет на все проверки |
| Тело | типизированный DTO, без чувствительных данных | типизированный DTO / DMR `ErrorModel` на 503 |

Оба пути живут **в корне** (ADR 0006 §1: `/healthz`, `/readyz` — «Django probes, не состояние worker/бота»; Caddy направляет probes до статического fallback), **вне** `api_v1_router` и **вне** OpenAPI-схемы: это эксплуатационные пробы, а не часть контракта контента (ADR 0014) и не источник TS-клиента.

Пробы **анонимны**: DMR-контроллеры не задают `auth`/`throttling`, `Controller.as_view()` снимает CSRF и `login_required` по умолчанию, GET не проверяется `CsrfViewMiddleware`.

### Что не входит

- Отдельный процесс / сервис `health`, FastAPI, отдельный Dishka-контейнер и compose-профиль: ADR 0015 §13 и §115 это отвергают (здоровье отдельного процесса не доказывает здоровье Django/worker). PyBot HealthAPI **не переносится**.
- Heartbeat worker/scheduler: проверяется process state по ADR 0015 §71 и #14 §2.2, транспорт ещё Proposed (ADR 0013). Django health его не заменяет.
- Проверка Telegram/VK/GitHub/GlitchTip: их отказ — деградация доставки, не причина restart storm (ADR 0015 §70, ADR 0005 §46).
- Структурное логирование (#27), env/PostgreSQL-конфигурация (#26/#14), CI (#26/Костян), генерация TS-клиента, адаптация домена (#25).
- Проверка media storage **в 0.2**: загрузка картинок — EDIT-02 (0.4), бэкап медиа — NFR-OPS-02 (0.4). ADR 0015 §69 требует проверки «**используемого**» хранилища; в 0.2 его нет. Порт `DependencyProbe` предусмотрен, адаптер подключается в 0.4 без правки ADR. Это не «урезание» контракта, а его точное чтение.
- Изменение Accepted ADR и PRD: данная спецификация реализует уже принятые решения. Потребность в отдельном health-процессе потребовала бы нового ADR по `CONTRIBUTING.md` (SDD) до реализации.

## Поведение и ограничения

1. `GET /healthz` → `200`, `{"status": "ok"}`. Ноль обращений к БД и внешним API; контроллер не получает зависимостей через Dishka. Это тонкий transport без application service — по ADR 0011 §31 «отдельные файлы и слои создаются по необходимости».
2. `GET /readyz` → контроллер получает `ReadinessProbe` через `FromDishka` (ADR 0011 §70). Провайдер зарегистрирован в `REQUEST`-scope и **не открывает соединение при создании/импорте** (ADR 0015 §41): соединение открывается лениво внутри `DatabaseProbe.check()`.
3. `DatabaseProbe` выполняет `SELECT 1` через `connections["default"].cursor()`, обёрнутый в `sync_to_async`, под `asyncio.wait_for` с общим бюджетом. Отмена `wait_for` не убивает поток, поэтому таймаут уровня драйвера (`connect_timeout` / `statement_timeout`) должен прийти из typed config в **#41** — см. Q2. На момент #28 `AppSettings` (`config/runtime.py`, PR #42) уже существует, но полей БД и таймаутов в нём нет, а `DATABASES` всё ещё захардкожен на SQLite без `OPTIONS`.
4. Любая зависимость != `ok` → `raise APIError(self.format_error("Service not ready"), status_code=503)`. `503` объявлен через `@modify(extra_responses=[ResponseSpec(Controller.error_model, ...)])`, иначе включённый `validate_responses=True` завернёт ответ. `semantic_responses` и parsers/renderers не трогаем.
5. Тела ответов не содержат DSN, путей, raw exception и traceback (ADR 0015 §69, NFR-SEC-03, ADR 0005 §37). После ребазы на PR #42 HTTP-логирование уже эмитит `request_finished` с `status_code=503`, `outcome=server_error`, `correlation_id` и `environment/release` (проверено HTTP-прогоном). Отдельного события `probe.unavailable` с именем отказавшей зависимости пока нет — см. Q5; «тихим» 503 больше не является.
6. Пробы не возвращают `HttpResponse` напрямую и не содержат `try/except` с возвратом ответа в теле эндпоинта (`$dmr`, `references/controllers.md`, review checklist).
7. Когда #26 добавит `build_404_handler` / `build_500_handler`, они останутся привязанными к `router.prefix = "api/v1/"`; root-пробы не должны перехватываться (проверить в smoke #14).
8. **Стыковка с #42 выполнена.** Ветка #28 перебазирована на `chore/27-cms-foundation-base` (PR #42). Теперь единственный composition root — `apps/core/apps.py`: он собирает `make_async_container(AppProvider(), HealthProvider(), context={AppSettings: ..., BoundLogger: ...})` и подменяет middleware на `async_only_middleware`. `config/asgi.py` контейнер не собирает и этим PR не изменяется. Конфликта при слиянии с #42 нет; код `apps/core/health/` и тесты не зависят от `AppSettings`/`BoundLogger`.

## Критерии приёмки

| ID | Исходные условия и действие | Ожидаемый результат | Как проверить |
| --- | --- | --- | --- |
| AC-1 | `GET /healthz` без сессии и токена | 200, `{"status":"ok"}`, **0 запросов к БД**, тело без DSN/путей | `django_assert_num_queries(0)` + `dmr_client` |
| AC-2 | `GET /readyz`, БД доступна | 200, `{"status":"ok","checks":[{"name":"database","status":"ok"}]}` | `dmr_client.get("/readyz")` |
| AC-3 | Отказ БД (`OperationalError` в probe) | `/healthz` = 200, `/readyz` = **503**, тело без raw exception / DSN / traceback | monkeypatch `DatabaseProbe._ping`, оба запроса |
| AC-4 | Зависшая зависимость | 503 в пределах таймаута, а не зависший запрос | monkeypatch с задержкой + короткий бюджет |
| AC-5 | `validate_responses=True`, ответ 503 | валидация проходит: получен 503, а не 422 от валидатора ответов | часть AC-3 + `just tests` |
| AC-6 | Запросы без cookie/CSRF-токена | 200 на обоих путях (анонимность) | явный тест без `enforce_csrf_checks` |
| AC-7 | Отказ БД, открыть последнюю статическую статью с локальными картинками | статья доступна (NFR-AVAIL-01/02) | **post-deploy smoke #14/runbook**, не unit-тест Django |
| AC-8 | Сверка OpenAPI | `/healthz` и `/readyz` отсутствуют в схеме, `just contract` без diff | `dmr_export_schema` + сверка после появления baseline |

Результаты проверок приложить к PR. Показать **красный AC-3 до реализации и зелёный после** (`CONTRIBUTING.md`, #26). Общий DoD — в [CONTRIBUTING.md](../../CONTRIBUTING.md).

## Открытые вопросы

| # | Вопрос | Владелец | Влияет |
| --- | --- | --- | --- |
| Q1 | Проверка storage в 0.2 отложена до 0.4; подтвердить трактовку «используемого media storage» | Илья + Костян | AC-2, границы |
| Q2 | **Проверено 24.11:** таймауты драйвера в `cms-foundation` **не приехали**. `AppSettings` (PR #42) содержит только `environment/debug/secret_key/allowed_hosts/release/log_level`; `.env.example` — без DB-параметров; `DATABASES` в `settings.py` — SQLite без `OPTIONS`. `connect_timeout` / `statement_timeout` и значение для `READINESS_TIMEOUT_SECONDS` должны появиться в **#41** (issue OPEN), после чего `di.py` берёт их из `get_settings()` вместо константы | #41 (Илья) + Костян | AC-4 |
| Q3 | Тело 503: `Controller.error_model` (выбрано) против собственного DTO | Илья | AC-3, runbook |
| Q4 | `AppSettings` (PR #42) пока не проверяет `DMR_SETTINGS`; скилл `$dmr` советует `validate_responses=False` в production, приоритет у проекта (`AGENTS.md`). Проверка с учётом prod-профиля и удаление рукописного `config_check.py` — **#41** | #41 (Илья) | не блокирует #28 |
| Q5 | HTTP-логи #42 уже дают `request_finished` с `status_code=503` / `outcome=server_error` / `correlation_id`. Нужен ли ещё `probe.unavailable` с именем отказавшей зависимости (`database` / `storage`) для дашбордов Loki — решить с Костей; на наблюдаемость 503 это уже не влияет | Илья + Костян | дашборды #14 |
| Q7 | ~~Перебазировать ли ветку #28 на `chore/27-cms-foundation-base`~~ — **решено**: ребаза выполнена, `HealthProvider` перенесён в единственный composition root `apps/core/apps.py`, см. п. 8 | Илья | снято |
| Q6 | Heartbeat worker/scheduler — отдельная работа #14, вне #28 | Костян / ADR 0013 | ничего в #28 |
