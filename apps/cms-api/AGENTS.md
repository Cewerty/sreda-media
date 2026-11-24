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
```

`STATIC_ROOT` — генерируемый артефакт, в Git не хранится. Подробности и
проверенные HTTP-ответы admin/Swagger — в [`README.md`](README.md).

### Quality gate: `justfile`

Из `apps/cms-api` (из корня — `just -f apps/cms-api/justfile <рецепт>`):

```bash
just            # = just check
just check      # проходящий набор: ruff, pyright, Django, config_check
just ci         # алиас check — именно это вызывает Костя в CI
just lint       # только ruff check --no-fix + ruff format --check
just types      # pyright
just django     # check, makemigrations --check, config_check.py
just format     # ruff format . (вручную, перед коммитом)
just hooks      # uv run lefthook install, один раз
```

Рецепты **вне `check`**, чтобы не ронять пайплайн до своих задач:
`just tests` (#26), `just boundaries` (#25, `tach.toml` пуст),
`just deploy-strict` (#26/#14, `check --deploy --fail-level WARNING` — сейчас
падает на `security.W*` и `mail.E001`, ждёт env-конфигурации),
`just migrations-lint` (нужен `DJANGO_QUALITY_GATE=1`),
`just django-upgrade` (кодмод, переписывает файлы — только вручную),
`just contract-baseline` / `just contract` (сверка OpenAPI без генерации
TS-клиента). Костя переносит рецепты в общий justfile монорепозитория как есть.

Локальные хуки (lefthook, Go, из dev-группы) вызывают `just lint` и `just check`.
Автоустановки через `prepare` намеренно нет, чтобы не ломать CI и exFAT.

Правила:

- **Типы — pyright, не mypy**: быстрее на прототипе. Уровень `basic` до #25.
  `django-stubs>=6.1.2` в dev-группе **без** extra `compatible-mypy` (он притащил
  бы mypy): pyright читает `.pyi` и понимает дескрипторы ORM. Одно послабление —
  `reportOptionalIterable = "warning"` на `UserAdmin.fieldsets` в донорском
  `admin.py`; вернуть в `error` после #25.
- Linters не пишут в файлы: `ruff check --no-fix`, `ruff format --check`.
  Форматирование — `uv run ruff format .` вручную, затем закоммитить.
- `D101`/`D102` обязательны в transport-слое (`apps/**/views.py`,
  `controllers.py`): оттуда DMR берёт описания OpenAPI. Остальные слои — через
  `per-file-ignores`; тесты больше не исключаются из линта целиком.
- Не подавлять проверки по существу через `# noqa` (как в `apps/cms-web/AGENTS.md`):
  `SECRET_KEY` читается из env, а не закрыт `S105`.
- `DMR_SETTINGS` использует `Settings` enum. Тихое отключение
  `validate_responses` / `semantic_responses` и пустые parsers/renderers ловит
  `config_check.py`.
- `django-upgrade` — кодмод, переписывает файлы, поэтому в гейт не включён:
  запускать вручную `uv run django-upgrade --target-version 6.1 apps config`.

## Что ещё не сделано

- Адаптация домена и auth — #25.
- Тесты Django (инструменты уже в dev-группе) и наполнение `tach.toml` — #26.
- CI/CD, path-фильтры и итоговый обязательный статус — зона Кости (#26).
  Гейт для него — `uv sync --frozen`, затем `just ci` из `apps/cms-api`.
- Генерация TS-клиента из OpenAPI (`openapi-typescript`) — отдельная задача;
  `--contract` пока только сверяет схему с `openapi.json`.
- `build_404/500/csrf_handler` и отдельный prod-профиль настроек отложены до
  введения полноценного объекта конфигурации (#26).
- Структурные логи — #27; `/healthz` и `/readyz` — #28; PostgreSQL и полная
  env-конфигурация — #26/#14 (ADR 0015). Частично сделано: `SECRET_KEY` и
  `DJANGO_DEBUG` читаются из env, есть `.env.example` и `config_check.py`.
- Явные зависимости `django`/`daphne` добавлены; `uv.lock` пересобран.
