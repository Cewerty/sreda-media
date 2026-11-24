# AGENTS — `apps/cms-api`

Бэкенд микро-CMS: Django + django-modern-rest (DMR) + Dishka, модульный монолит
(ADR 0004, ADR 0011). Сначала читай корневой [`AGENTS.md`](../../AGENTS.md),
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) и [`docs/architecture.md`](../../docs/architecture.md) —
они задают границы, роли и порядок согласования. Этот файл уточняет их для CMS
и не отменяет принятые ADR.

> Основа перенесена из DHR в #24, предметная область донора ещё не заменена (#25).
> Карта переноса и известные расхождения — [`docs/dhr-transfer.md`](../../docs/dhr-transfer.md).

## Официальные скиллы DMR

В репозиторий добавлены официальные Agent Skills `django-modern-rest==0.16.0`,
поставляемые самим пакетом: [`.agents/skills/`](../../.agents/skills/README.md).
Используй их при работе с DMR-кодом, не изобретай паттерны заново.

| Скилл | Когда |
| --- | --- |
| `$dmr` | **Основной.** Написание controllers/routers/DTO, auth, throttling, ошибки, OpenAPI, тесты; ревью существующего DMR-кода на типовые ошибки |
| `$dmr-upgrade` | При обновлении версии `django-modern-rest` в `uv.lock` или если после апгрейда сломались импорты из `dmr` |
| `$dmr-openapi-skeleton` | Spec-first: генерация транспортного каркаса из `openapi.json` (ADR 0004 §11 — OpenAPI как источник TS-клиента) |
| `$dmr-from-drf`, `$dmr-from-django-ninja`, `$dmr-from-dj-rest-auth` | Миграции **с других фреймворков**. У нас DMR выбран сразу (ADR 0004), мигрировать нечего — не применяй без отдельной задачи |

Документация для LLM той же версии: <https://django-modern-rest.readthedocs.io/llms.txt>
(индекс), <https://django-modern-rest.readthedocs.io/llms-full.txt> (полный текст
со всеми примерами), отдельные страницы — `.md` вместо `.html` в URL.

**Приоритет при конфликте.** Скилл — помощник, а не решение. Если его рекомендация
расходится с Accepted ADR или PRD, действует проект, а расхождение фиксируется
и передаётся владельцу решения по `CONTRIBUTING.md` (правило корневого
`AGENTS.md`). Конкретно здесь не переносить из скиллов:

- JWT/token-auth вместо Django database-backed sessions и CSRF (ADR 0009 §1);
- парольный flow и роль из тела запроса — у нас вход через Telegram по
  приглашению, `ProviderIdentity`, unusable password (ADR 0009, NFR-SEC-01);
- SQLAlchemy/Alembic или «универсальную» структуру слоёв вместо Django ORM,
  Django Migrations и границ `content`/`accounts`/`publishing`/`notifications`
  (манифест §4.1, ADR 0011);
- Redis / не in-memory cron для фоновых задач (ADR 0013 Proposed, ADR 0012).

После применения скилла обязательны ревью, проверка типов и тесты — это прямое
требование официальной документации DMR.

## Границы и структура

- `apps/cms-api` владеет состоянием CMS и серверными правилами предметной области.
  `apps/cms-web` (React) общается только по HTTP-контракту DMR/OpenAPI.
- Слои (ADR 0011): тонкий transport (DMR controller) → application service
  (use case, права, `transaction.atomic()`) → rich Django-модель / domain service →
  Django ORM → PostgreSQL. Бизнес-переходы не реализуются в controllers,
  serializers, middleware, signals или `save()`-хуках.
- DI/IoC через Dishka (`dmr-dishka`, `FromDishka`), composition roots по
  entrypoints. Контейнер не передаётся в бизнес-логику как service locator.
- Импорты между Django-модулями проверяет `tach` (настройка — #26). `tach`
  не заменяет проверку прав во время исполнения.
- Сейчас в коде только донорские `apps/core` и `apps/users`. Целевые приложения —
  `content`, `accounts`, `publishing`, `notifications` (ADR 0011) — появятся в #25.

## Команды

Из **корня** монорепозитория (uv workspace):

```bash
uv sync --all-packages     # без --all-packages зависимости cms-api не ставятся
```

Затем из `apps/cms-api`:

```bash
uv run manage.py check
uv run manage.py migrate --plan
uv run manage.py migrate
uv run manage.py collectstatic --noinput   # обязательно при DEBUG=False
uv run manage.py runserver
uv run ruff check .
```

`STATIC_ROOT` — генерируемый артефакт, в Git не хранится. Подробности и
проверенные HTTP-ответы admin/Swagger — в [`README.md`](README.md).

## Что ещё не сделано

Адаптация домена и auth — #25; Django quality gate / tach / CI — #26;
структурные логи — #27; `/healthz` и `/readyz` — #28; env-конфигурация,
PostgreSQL и явные зависимости `django`/`daphne` — #26/#14 (ADR 0015).
