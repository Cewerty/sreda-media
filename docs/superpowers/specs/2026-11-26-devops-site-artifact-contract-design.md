# DevOps: контракт артефакта статической витрины

> **Статус:** Approved 26.11.2026  
> **Владелец:** Костян (Zisvit), DevOps  
> **Ветка:** локальная работа в `devops/chaos-self-heal`, перемотанной до `origin/main`; PR не создаётся  
> **Ссылки:** #5 #9 #14 #47 #48

## Контекст и проблема

PR #16 влит в `main`, поэтому `apps/site` теперь существует и `just build-site` реально собирает Astro 6. Фронтенд кладёт результат в `apps/site/dist`, а вся наша DevOps-цепочка исторически ожидала корневой `dist`:

- `scripts/sign-artifact.sh dist` и `scripts/verify-artifact.sh dist`;
- `scripts/deploy-static.sh deploy dist ...`;
- `.github/workflows/deploy.yml` и `.github/workflows/provenance.yml`;
- шаг подписи в `.github/workflows/site-build.yml` имеет guard `if [ -d dist ]` и сейчас честно пропускается.

Кроме того, `deploy-static.sh` требует `404.html`, но issue #5 ещё открыта — страницу 404 добавляет владелец фронтенда. Значит, полный контракт выкладки пока не может быть зелёным, и это нельзя выдавать за успех.

## Цель

Обеспечить корректный путь артефакта от реальной Astro-сборки до подписи, верификации и gated deploy, не меняя фронтенд-исходники и не включая прод-гейты.

## Вне границ

- Изменение `apps/site/**`, чужого PR #16 и чужого PR #50.
- Создание страницы `404.html` — это issue #5 и зона фронтенда.
- Включение `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `ENABLE_SELF_HEAL`, `SREDA_SITE_URL`.
- Изменение GitHub Environment, variables, secrets, branch protection.
- Правка `ci.yml`, `check_log_schema.py`, `CONTRIBUTING.md` в этом спеке — только если потребуется синхронизация документации.
- Новый PR, новая удалённая ветка, worktree, работа с `serv`.

## Архитектура

Источник правды остаётся прежним:

1. `just build-site` (авторитетная часть Ильи) вызывает `pnpm --filter site build` и оставляет вывод в `apps/site/dist`.
2. Новый `scripts/stage-site.sh` нормализует вывод: копирует `apps/site/dist` в корневой `dist`, не меняя исходники и не выполняя сборку сам.
3. Новый `scripts/check_site_artifact.py` читает корневой `dist` и проверяет контракт артефакта.
4. Существующие `sign-artifact.sh`, `verify-artifact.sh`, `deploy-static.sh` остаются без изменений и продолжают работать с корневым `dist`.

Поток данных

```text
just build-site
  → pnpm --filter site build
  → apps/site/dist
  → just stage-site
  → dist/
  → just check-site-artifact
  → sign-artifact.sh / verify-artifact.sh / deploy-static.sh
```

## Компоненты

### `scripts/stage-site.sh`

- Исполняемый bash-скрипт, только локальные файлы.
- Находит корень репозитория относительно своего пути и переходит в него.
- Обязательно требует `apps/site/dist/index.html`; отсутствие — FAIL exit 1.
- Если корневой `dist` является симлинком — FAIL exit 1, чтобы не удалить чужую цель.
- Удаляет только корневой `dist` и создаёт его заново через `cp -a apps/site/dist/. dist/`.
- Печатает число файлов в получившемся `dist`.
- Не использует сеть, секреты, `sudo`, systemd, `/srv`.

### `scripts/check_site_artifact.py`

- stdin/stdout только на русском, без печати секретов.
- Опциональный `argv[1]` задаёт корень репозитория — используется негативными тестами.
- Обязательные условия:
  - `dist/index.html` существует и не пустой;
  - `dist/404.html` существует и не пустой.
- При отсутствии `404.html` печатает отдельное пояснение: страница 404 описана в issue #5 и находится в зоне фронтенда.
- Exit 1 только на нарушение контракта; exit 0 при полном контракте.
- Не проверяет хэш и подпись: это ответственность `verify-artifact.sh`.

### Рецепты `justfile`

- `stage-site`: вызывает `bash scripts/stage-site.sh`.
- `check-site-artifact`: вызывает `python3 scripts/check_site_artifact.py`.
- Оба рецепта добавляются в конец justfile рядом с другими artifact-рецептами и **не включаются в `verify`**, чтобы обязательный `ci` не стал красным из-за открытой issue #5.

### Workflow

- `.github/workflows/site-build.yml`: после шага `Build site` добавляется шаг `Stage site artifact` с `just stage-site`. Существующий шаг подписи остаётся `continue-on-error: true`, но guard `if [ -d dist ]` теперь проходит, и подпись подготавливается по-настоящему.
- `.github/workflows/deploy.yml`: заменяет `just build-site` на `just stage-site`; перед `Prepare hash and optional signature` добавляется `just check-site-artifact`; guard `vars.ENABLE_DEPLOY == 'true'` и `dry_run` остаются прежними.
- `.github/workflows/provenance.yml`: та же замена и тот же чекер перед подписью; guard `vars.ENABLE_PROVENANCE == 'true' && github.ref == 'refs/heads/main'` остаётся.
- YAML для `run:` пишется block scalar либо безопасной строкой без `#` посередине, чтобы shellcheck в CI не ловил незакрытую кавычку — учёт замечания Ильи по `lighthouse.yml`.

## Обработка ошибок

- Нет `apps/site/dist` или `index.html` — `stage-site` падает с явным сообщением; сборка не считается готовой.
- `dist` — симлинк — отказ без удаления.
- Пустой `dist`, отсутствующий `index.html` или `404.html` — чекер падает с exit 1.
- Отсутствие `404.html` не маскируется: чекер явно называет issue #5.
- Подпись без `cosign` остаётся опциональной, хэш `artifact.sha256` создаётся всегда — текущий контракт `sign-artifact.sh` сохраняется.
- Ни один из новых шагов не включает гейты и не меняет настройки GitHub.

## Тестирование

Локальные проверки:

- `bash -n scripts/stage-site.sh`, `python3 -m py_compile scripts/check_site_artifact.py`.
- Позитив: `just stage-site`, затем `dist/index.html` существует; временно создать `dist/404.html`, чекер возвращает ok; временный файл удалить.
- Негативы:
  - пустой `dist` → FAIL exit 1;
  - нет `404.html` → FAIL с упоминанием issue #5;
  - `dist` — симлинк → stage FAIL;
  - нет `apps/site/dist` → stage FAIL;
  - непустой временный root с битыми файлами → FAIL.
- Полный `just verify` на состоянии `origin/main`: Astro собирается по-настоящему, CMS API gate, frontend-тесты, ruff/pyright, actionlint, zizmor, gitleaks, mkdocs strict — всё зелёное.
- Дополнительно: `config_lint.py`, `check.py`, `check_links.py`, `audit_workflows.py`, `check_runbook_commands.py`, `audit_hardening`, `check_workflow_hardening.py`, `actionlint`, `zizmor`, `git diff --check`, grep на mixed-language artefacts.

## Критерии приёмки

1. После `just build-site` и `just stage-site` корневой `dist` содержит результат реальной Astro-сборки.
2. `sign-artifact.sh dist` и `verify-artifact.sh dist` работают с этим каталогом без правки скриптов.
3. `site-build.yml` больше не пропускает подпись из-за отсутствия корневого `dist`.
4. `deploy.yml` и `provenance.yml` используют один и тот же путь артефакта и проверяют контракт перед подписью.
5. `just verify` зелёный с реальным `apps/site`.
6. Гейты, алерты, `serv`, чужие PR и фронтенд-исходники не тронуты.
7. Новый PR не создан; изменения остаются локальными до явной команды пользователя.

## Связь с 12 Factor App

- **Config:** адрес и флаги остаются в окружении, не в репозитории.
- **Build/release/run:** `build-site` собирает, `stage-site` подготавливает артефакт, `deploy` публикует только при явном gate.
- **Dev/prod parity:** один и тот же корневой `dist` используется локально и в CI.
- **Disposability:** корневой `dist` полностью пересоздаётся и может быть удалён без потери исходников.
