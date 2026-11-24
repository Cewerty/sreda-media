# `cms-api` — микро-CMS Sreda Media

Django + django-modern-rest (DMR) + Dishka. Часть монорепозитория (ADR 0007).
Продуктовые требования — [`docs/prd.md`](../../docs/prd.md), архитектурные решения —
[`docs/adr/`](../../docs/adr/), границы приложений — ADR 0011.

> Основа перенесена из `Cewerty/Digital-hire-reports` @
> `ab3a3ca9d74f896405f0181d2c412c7e37b095c7` (issue #24). Предметная область
> донора (`apps/users` с парольным flow, роли `member|admin`) — временная и
> заменяется в #25 по ADR 0009/0010. Карта переноса — [`docs/dhr-transfer.md`](../../docs/dhr-transfer.md).

## Запуск

Python 3.14 (`.python-version`), менеджер — [uv](https://docs.astral.sh/uv/).
Workspace объявлен в корневом `pyproject.toml`, поэтому зависимости ставятся
из корня монорепозитория:

```bash
uv sync --all-packages     # важно: без --all-packages корневой виртуальный
                           # проект не тянет зависимости cms-api
```

Дальше команды выполняются из `apps/cms-api`:

```bash
uv run manage.py check
uv run manage.py migrate --plan
uv run manage.py migrate
uv run manage.py collectstatic --noinput
uv run manage.py runserver
```

## Конфигурация и диагностика

Скопируй `.env.example` в `.env` рядом с `manage.py`. Переменные процесса
имеют приоритет. Для production выставь `DJANGO_ENV=production`,
`DJANGO_DEBUG=0`, собственный `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`
через запятую и `RELEASE` (тег или SHA). Перед запуском выполни
`uv run python config_check.py`. Ошибка укажет имя параметра и правило.

CMS возвращает `X-Correlation-ID` в HTTP-ответе. Найди этот UUID в поле
`correlation_id` события `request_finished` в stdout процесса.
`LOG_LEVEL` управляет остальными прикладными сообщениями (по умолчанию INFO).
[Спецификация и пример события](../../docs/specs/cms-runtime-config-and-logging.md).

## Статика

`STATIC_ROOT = apps/cms-api/static/` — **генерируемый** артефакт `collectstatic`,
в Git не хранится (`.gitignore`). Исходники статики приезжают из установленных
пакетов (`django.contrib.admin`, `dmr`), поэтому папка полностью восстанавливается:

```bash
uv run manage.py collectstatic --noinput
```

- `DEBUG=True` + `runserver`: статика отдаётся finders'ами, `collectstatic` не обязателен.
- `DEBUG=False`: WhiteNoise (`CompressedStaticFilesStorage`) раздаёт из `STATIC_ROOT`,
  поэтому `collectstatic` — обязательный шаг сборки/выпуска (ADR 0015 §1).

Проверено в обоих режимах: `/admin/login/`, `/docs/swagger/`, `/docs/openapi.json/`
и все их ассеты отвечают 200.

## Агентские скиллы DMR

В репозиторий добавлены официальные Agent Skills `django-modern-rest`, которые
поставляются внутри самого пакета: `.agents/skills/` в корне (6 скиллов,
34 файла, версия 0.16.0 из `uv.lock`). Основной — `$dmr` для написания и ревью
DMR-кода. Происхождение, лицензия MIT, порядок обновления и нюанс с `--copy` на
exFAT — в `.agents/skills/README.md`; правила применения с учётом наших ADR —
в [`AGENTS.md`](AGENTS.md).

Официальная установка: `uvx library-skills --all -y --copy --no-tool-skill`
(из корня, после `uv sync --all-packages`).

## Что пока не сделано

Это перенесённая основа, а не готовый CMS. Открыто и вынесено в отдельные задачи:

- **#25** — предметная область: `Content`/`ContentKind`/payload (ADR 0010), статусы
  (ADR 0004 §2), роли PRD, `ProviderIdentity` и вход через Telegram без паролей
  (ADR 0009). Текущие `POST /api/v1/users/` и `PUT /api/v1/users/<id>/` создают
  пользователя с паролем и меняют пароль — это донорский прототип, не AUTH-01…04.
- **#26** — тесты Django и наполнение `tach.toml` (ADR 0011), CI/CD Кости,
  полная env-конфигурация. Гейт уже добавлен: `justfile`, `config_check.py`,
  pyright, ruff, dev-зависимости, `lefthook.yml`, `uv.lock`.
  Команда для CI — `just check` (алиас `just ci`).
- **#28** — `/healthz` и `/readyz`. PostgreSQL — #26/#14.
