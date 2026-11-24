# Перенос основы DHR в монорепозиторий

Артефакт по issue #24 (эпик #21). Инвентаризация кода, лицензий, зависимостей и
истории источника; карта «источник → путь»; способ проверки.

Требования: NFR-MAINT-01, NFR-MAINT-02, NFR-SEC-03. Решения: ADR 0007 (монорепозиторий),
ADR 0004 §12 (что берётся из DHR), ADR 0011 (границы CMS), ADR 0015 (эксплуатация).

## 1. Источник

| | |
| --- | --- |
| Донор | `Cewerty/Digital-hire-reports` (публичный) |
| Исходный commit | `ab3a3ca9d74f896405f0181d2c412c7e37b095c7` |
| Ветка | `main` |
| Сообщение коммита | `fix: задал title для OpenAPI и Swagger через OpenAPIConfig` |
| Лицензия донора | отсутствует (`license: null` в GitHub API) |
| Автор донора | Cewerty (Илья) — тот же, что владелец `cms-api` |
| История источника | сохранена в донорском репозитории; в монорепозиторий переносится снимок файлов, вложенный `.git` удалён |

Донор — собственный проект автора, поэтому перенос в монорепозиторий под GPL-3.0
не требует согласования с третьими лицами. Отсутствие LICENSE в доноре
зафиксировано здесь, чтобы при передаче проекта (G-5) было видно происхождение кода.

## 2. Карта переноса

| Донор (`Digital-hire-reports` @ `ab3a3ca`) | Монорепозиторий |
| --- | --- |
| `src/`, `index.html` | `apps/cms-web/src/`, `apps/cms-web/index.html` |
| `package.json` | `apps/cms-web/package.json` (имя `my-app` → `@sreda/cms-web`) |
| `biome.json`, `postcss.config.js`, `tailwind.config.js` | `apps/cms-web/` (без изменений; из `biome.json` убраны ignore `backend/**`, `django/**`, `manage.py`) |
| `tsconfig*.json`, `vite.config.ts`, `vitest.config.ts` | `apps/cms-web/` (`vite.config.ts`: убран донорский `base` `/Digital-hire-reports/`) |
| `apps/`, `config/`, `manage.py` | `apps/cms-api/apps/`, `apps/cms-api/config/`, `apps/cms-api/manage.py` |
| `pyproject.toml` | `apps/cms-api/pyproject.toml` (имя `backend` → `cms-api`, добавлен `[tool.uv] package = false`) |
| `uv.lock` | `uv.lock` в корне (lock workspace) |
| `.python-version`, `tach.toml` | `apps/cms-api/` |
| `.gitattributes` | `.gitattributes` в корне |
| `docs/decisions.md`, `docs/design-system.md` | `apps/cms-web/docs/` (справка, с пометкой о происхождении) |

Новое в монорепозитории: корневые `package.json`, `pnpm-workspace.yaml`,
`pyproject.toml` (uv workspace), `.gitignore`; `apps/cms-web/AGENTS.md`,
`apps/cms-api/README.md`, этот файл.

## 3. Что удалено

| Удалено | Почему |
| --- | --- |
| Вложенный `.git` (полный клон донора) | Git предупреждал «adding embedded git repository»: клоны монорепозитория не получили бы содержимое. Источник зафиксирован в §1 |
| `static/` — 289 файлов, ~13,4 МБ | Результат `collectstatic`, генерируемый артефакт. Восстановлен и сверен один-в-один (§5) |
| `vercel.json` | Донорский деплой. Развёртывание — VPS + Caddy (ADR 0006), зона Костяна (#9, #14) |
| `package-lock.json` | npm заменён на pnpm workspaces (ADR 0007); lock — `pnpm-lock.yaml` |
| `README.md`, `SPEC.md`, `docs/architecture.md`, `docs/implementation-plan.md`, `docs/agents_pipeline.md`, `docs/task-template.md`, `docs/prompts/` | Донорские требования и SDD-процесс («Архитектор/Шиха», задачи T01–T07, найм/1С). Не актуальны, переписываются под Sreda |
| Донорский `AGENTS.md` | Предписывал npm, моки `demoData` и роли донорского процесса; конфликтовал с корневым `AGENTS.md`. Заменён на `apps/cms-web/AGENTS.md` |
| `config/taskiq_app.py`, `apps/core/logging.py`, `apps/users/tests.py` | Пустые заглушки, никем не импортируются. TaskIQ/Redis не переносятся автоматически (манифест §3, ADR 0013 Proposed). Логи — #27, тесты — #26 |

## 4. Зависимости

**Python** (`apps/cms-api/pyproject.toml`, `requires-python >= 3.14`, lock — корневой `uv.lock`):

| Объявлено | Разрешено |
| --- | --- |
| `django-modern-rest[jwt,msgspec,openapi,pydantic]>=0.16.0` | 0.16.0 |
| `dmr-dishka>=0.1.1` | 0.1.1 |
| `dishka>=1.10.1` | 1.10.1 |
| `whitenoise>=6.12.0` | 6.12.0 |
| `uvicorn>=0.54.0` | 0.54.0 |
| `ruff>=0.17.1` | 0.17.1 |

Ключевые транзитивные: `django==6.1.2`, `daphne==4.2.3`, `pydantic==2.14.1`,
`msgspec==0.22.0`, `twisted==26.4.0`, `cryptography==50.0.2`. Всего 58 пакетов.

Находка для #26: `django` и `daphne` используются напрямую (`INSTALLED_APPS`,
миграции, `manage.py`), но объявлены только транзитивно. Их стоит вынести
в явные зависимости.

**JS/TS** (`apps/cms-web/package.json`, lock — корневой `pnpm-lock.yaml`):

- runtime: `react`/`react-dom` ^18.3.1, `react-router-dom` ^6.26.2,
  `react-markdown` ^9.0.1, `@radix-ui/react-alert-dialog` ^1.1.2,
  `@radix-ui/react-collapsible` ^1.1.1, `@radix-ui/react-progress` ^1.1.0,
  `@radix-ui/react-slot` ^1.1.0, `lucide-react` ^0.454.0, `sonner` ^1.5.0,
  `clsx` ^2.1.1, `class-variance-authority` ^0.7.1, `tailwind-merge` ^2.5.2;
- dev: `typescript` ^5.6.2, `vite` ^5.4.8, `vitest` ^2.1.9, `@biomejs/biome` ^1.9.4,
  `tailwindcss` ^3.4.13, `@tailwindcss/typography` ^0.5.15, `postcss` ^8.4.47,
  `autoprefixer` ^10.4.20, `@vitejs/plugin-react` ^4.3.2, `@types/*`.

Biome, tsc и Vitest перенесены без изменений, как и предписано ADR 0004 §12.

## 5. Лицензии

- Монорепозиторий: GPL-3.0 (`LICENSE` в корне).
- Донор: LICENSE отсутствует, автор тот же (§1).
- Сторонние бандлы, которые лежали в донорском `static/` (jQuery, select2, xregexp,
  Swagger UI, ReDoc, Scalar, Stoplight), **удалены вместе с `static/`** и в Git
  не переносятся. Они приходят из установленных пакетов Django/DMR при
  `collectstatic` и несут свои лицензии внутри пакетов. Отдельных вендоренных
  копий в репозитории нет.
- Зависимости из npm/PyPI сохраняют свои лицензии; отдельной инвентаризации
  по каждой не требуется, так как всё приходит через пакетные менеджеры по lock-файлам.

## 6. Воспроизводимость и проверки

```bash
# Python (из корня)
uv sync --all-packages
# затем из apps/cms-api
uv run manage.py check
uv run manage.py migrate --plan
uv run manage.py collectstatic --noinput
uv run manage.py runserver

# JS/TS (из корня)
pnpm install
pnpm check:cms      # biome без записи
pnpm test:cms       # vitest
pnpm build:cms      # tsc -b && vite build
```

Результаты на момент переноса:

- `manage.py check` — `System check identified no issues (0 silenced)`.
- `migrate --plan` — полная цепочка, включая `users.0001_initial`,
  `users.0002_alter_customuser_options_alter_customuser_table`,
  `users.0003_customuser_role_customuser_uid`.
- `manage.py migrate` — все миграции применены (`OK`), `showmigrations users`
  показывает `[X]` для всех трёх. Миграции переносимы: смена SQLite → PostgreSQL
  их не требует (только `CreateModel`/`AlterModelOptions`/`AlterModelTable`/`AddField`,
  без `RunSQL` и диалект-специфики).
- `ruff check .` — `All checks passed!`.
- `collectstatic --noinput` — 146 файлов скопировано, 143 пост-обработано;
  на диске 289 файлов. Сверка с донорским списком: **289 против 289,
  отсутствующих 0, лишних 0**.
- HTTP-проверка в двух режимах (`DEBUG=True` и `DEBUG=False` + WhiteNoise):
  `/admin/login/`, `/docs/swagger/`, `/docs/openapi.json/` — 200;
  все 7 ассетов admin и все 7 ассетов Swagger UI — 200.
- Фронтенд (чистая копия на NTFS): `pnpm install` — успешно;
  `pnpm check:cms` — `Checked 39 files. No fixes applied.`;
  `pnpm test:cms` — 3 файла, **45 тестов passed**;
  `pnpm build:cms` — `tsc -b && vite build`, собрано `dist/`
  (index.html 1.07 kB, CSS 45.93 kB, JS 494.10 kB);
  `pnpm verify:cms` — успешно.
- Форматирование: `biome check --write src` поправил 2 файла
  (`src/vite-env.d.ts`, `src/router.tsx`), после чего проверка чистая.
  Это штатный шаг донорского процесса (`npm run format` перед коммитом),
  выполненный при переносе; логика не менялась.

### Находки по инструментам

- `uv sync` без `--all-packages` не ставит зависимости `cms-api`: корневой
  проект виртуальный (`package = false`) и не имеет собственных зависимостей.
  В инструкциях зафиксировано `uv sync --all-packages`.
- pnpm 12 по умолчанию блокирует postinstall-скрипты (`ERR_PNPM_IGNORED_BUILDS`).
  `esbuild` и `@biomejs/biome` ставят платформенный бинарник именно постинсталлом,
  поэтому в `pnpm-workspace.yaml` явно разрешены через `allowBuilds`
  (формат pnpm 12; `onlyBuiltDependencies` — формат pnpm 10).
- `django` и `daphne` используются напрямую, но объявлены только транзитивно — #26.

### Миграции: не сносить по привычке из Alembic

Инстинкт «при смене SQLite → PostgreSQL проще снести все миграции и сделать
один baseline» верен для **Alembic**: ревизии там — линейная цепочка,
сгенерированная сравнением SQLAlchemy metadata с живой БД, часто с сырым
диалектным DDL (`op.execute`, `op.alter_column`, batch-эмуляция `ALTER TABLE`
для SQLite). `alembic_version` привязан к конкретной схеме, и autogenerate на
другом движке даёт ложный diff. Поэтому сброс `versions/` + новый initial —
обычная практика, особенно на тестовых данных.

В Django механизм другой: миграции — это не DDL-скрипты, а **граф операций над
состоянием моделей**, а DDL собирается schema editor'ом под текущий
`DATABASES.ENGINE` в момент применения. `django_migrations` — просто журнал
применённого, который на новой БД создаётся заново. На пустой PostgreSQL
`migrate` воспроизводит граф с нуля; «переносить историю» нечего, потому что
БД ещё нет и данные тестовые. Смена движка — одна строка в settings + `migrate`.

Проверено: в трёх донорских миграциях только `CreateModel`,
`AlterModelOptions`, `AlterModelTable`, `AddField` — без `RunSQL`, `RunPython`
и диалект-специфики, так что они применимы на PostgreSQL как есть.

Это зафиксировано принятыми решениями, а не только устройством Django:
архитектурный манифест §4.1 («SQLAlchemy, `asyncpg` и Alembic не являются
частью persistence-стека CMS»), ADR 0004 §11 («SQLAlchemy session и Alembic
из PyBot не переносятся»), ADR 0015 §3 («Django migration history нового
проекта не сбрасывается по примеру перехода PyBot с SQLite», PostgreSQL-парти для
тестов создаётся Django-миграциями, не только ORM metadata).

**Сквош до первого прода всё равно допустим и дёшев** (данных нет, БД нет) —
но это осознанное решение «хочу чистую историю для гринфилда», а не следствие
перехода на PostgreSQL. Если его принимают, фиксируют как решение в #25/#26 до
появленияproduction-БД; после появления БД снос истории уже нарушает ADR 0015 §3.

Где Django-миграции действительно ломаются при смене диалекта: `RunSQL` с
диалектным SQL, `RunPython` с сырыми запросами, специфичные типы/констрейнты.
Тогда правят сами миграции, а не сбрасывают историю.

### Ограничение файловой системы

pnpm по умолчанию строит изолированный `node_modules` на симлинках. На exFAT/FAT32
(внешний диск) симлинки не поддерживаются, и `pnpm install` падает с
`Failed to create symlink … os error 1`. Проверка фронтенда выполнена на чистой
копии в NTFS. На NTFS/Linux установка работает штатно; владельцам exFAT нужно
либо перенести репозиторий на NTFS, либо ставить зависимости внутри
`apps/cms-web` с `--ignore-workspace`. Решение о раскладке `node_modules`
согласовать с Костей в #26/#14.

## 7. Известные расхождения с Accepted ADR

Перенос (#24) не адаптирует предметную область. Расхождения зафиксированы явно
и переданы в отдельные задачи, а не оставлены молча:

| Расхождение | ADR / требование | Задача |
| --- | --- | --- |
| `CustomUser(AbstractUser)` с `username`/`email`/`password`, роли `member\|admin` | ADR 0009 (Telegram-ID, `ProviderIdentity`, unusable password), роли PRD §4 | #25 |
| `POST /api/v1/users/` создаёт пользователя с паролем; `PUT /api/v1/users/<id>/` меняет пароль; `PATCH` принимает роль из тела запроса | ADR 0009 §1–2, NFR-SEC-01 («нет паролей»), AUTH-01…04 | #25 |
| `AUTH_PASSWORD_VALIDATORS` в settings | ADR 0009, NFR-SEC-01 | #25 |
| Донорская предметка в UI: кандидаты, найм, отчёты, 1С; `demoData.ts` с вымышленными именами и `@example.com` | ADR 0004 §12 («выкидывается»), ADR 0010 | #25, #29 |
| Донорский брендинг: `Digital Hire API` в `config/urls.py`, заголовок в `index.html` | ADR 0004 | #25 |
| `SECRET_KEY` захардкожен, `DEBUG=True`, `ALLOWED_HOSTS=["*"]`, SQLite | ADR 0015 §2–3, NFR-SEC-03 | #26, #14 |
| Нет тестов Django, нет `tach`-конфигурации, нет CI CMS | ADR 0011, NFR-MAINT-01 | #26 |
| Нет структурных логов, `/healthz`, `/readyz` | ADR 0015 §4, ADR 0005 | #27, #28 |
| Три донорские миграции под SQLite; переход на PostgreSQL их не требует (операции переносимы, без `RunSQL`), снос по привычке из Alembic не применяется (см. §6); сквош — отдельное осознанное решение до первого прода | Манифест §4.1, ADR 0004 §11, ADR 0015 §3 | #25, #26 |

Секретов и персональных данных донора в перенесённом коде нет: `SECRET_KEY` —
сгенерированный Django dev-плейсхолдер (`django-insecure-…`), контакты в
`demoData.ts` вымышленные, домен `example.com` зарезервирован RFC 2606.
Дампов БД и реальных данных не переносилось.
