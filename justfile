# Единая точка входа для локальных проверок и CI (ADR 0007, issue #26).
# Вызов: just <recipe>. Список: just --list.
set shell := ["bash", "-uc"]

# Всё сразу: то, что обязательно в CI. Версия Ильи из PR #45 — авторитетная.
verify: check check-logs check-alerts install lint-web types test-web build-web api-check config-lint workflows-lint secrets build-site
    @echo "just verify: все проверки пройдены"

# Зависимости чистого checkout (pnpm workspaces + uv workspace).
install:
    pnpm install --frozen-lockfile
    uv sync --frozen

# Локальный .env для CMS API (по CONTRIBUTING.md).
api-env: install
    if [ ! -f apps/cms-api/.env ] && [ -f apps/cms-api/.env.example ]; then cp apps/cms-api/.env.example apps/cms-api/.env; fi

# Локальный PostgreSQL 18 для verify: поднимается только вне CI и только если есть docker.
api-db-up:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "${CI:-}" = "true" ]; then
        echo "CI: PostgreSQL уже запущен сервисом, локальный контейнер не нужен"
        exit 0
    fi
    if command -v docker >/dev/null 2>&1; then
        docker compose -f deploy/dev/postgres.yml up -d --wait
    else
        echo "docker не найден: локальный PostgreSQL не поднят"
    fi

api-db-down:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v docker >/dev/null 2>&1; then
        docker compose -f deploy/dev/postgres.yml down
    fi

# Авторитетная версия Ильи из PR #45: полный вложенный gate.
# Локально используем поднятый контейнер на 55432, в CI — сервис на 5432.
api-check: api-env api-db-up
    #!/usr/bin/env bash
    set -euo pipefail
    port=5432
    if [ "${CI:-}" != "true" ] && command -v docker >/dev/null 2>&1; then port=55432; fi
    cd apps/cms-api && uv sync --frozen && POSTGRES_PORT="$port" UV_NO_SYNC=1 just check

# Документация, ADR, ссылки, CODEOWNERS и шаблонные секреты.
check:
    python3 scripts/check.py

check-logs:
    python3 scripts/check_log_schema.py

# Provisioning Grafana Alerting: секреты через env, правила отключены до сайта и адреса.
check-alerts:
    uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py

# Линтеры кода: Python (ruff) и JS/TS (Biome).
lint:
    uv run --project apps/cms-api ruff check apps/cms-api
    just lint-web

lint-web:
    pnpm --filter @sreda/cms-web check

# Валидация конфигурационных файлов репозитория.
config-lint:
    python3 scripts/config_lint.py

# actionlint + zizmor для workflow-файлов.
workflows-lint:
    bash scripts/workflows_lint.sh

# gitleaks по всей истории репозитория (issue #13, замечание 2).
secrets:
    go install github.com/zricethezav/gitleaks/v8@v8.30.1
    "$(go env GOPATH)/bin/gitleaks" git --redact --no-banner

# Проверка типов CMS Web (DoD: linters + types, без записи в исходники).
types: install
    pnpm --filter @sreda/cms-web exec tsc -b --noEmit
    pnpm --filter @sreda/cms-web test:types

# Сборка CMS Web (DoD: сборка затронутого компонента).
build-web: install
    pnpm --filter @sreda/cms-web build

# Тесты доступных компонентов.
test: install test-web
    # cms-api: тесты из PR #42 пока не в main (stacked PR на chore/27-cms-foundation-base).
    if [ -d apps/cms-api/tests ]; then uv run --project apps/cms-api python -m pytest apps/cms-api/tests -q; else echo "cms-api: тестов пока нет в main (PR #42)"; fi

test-web:
    pnpm --filter @sreda/cms-web test

# Покрытие: пока заглушка, чтобы не создавать иллюзию полноценного прогона.
cov: test
    @echo "cov: отчёт по покрытию ещё не настроен (issue #26)"

# Валидация материалов и медиа перед сборкой (ADR 0014, issue #6).
check-content:
    python3 scripts/validate_content.py

# Сборка сайта: реальная сборка Astro включается, когда apps/site попадёт в main (PR #16).
build-site: check-content
    test -f docs/adr/0014-cross-stack-content-contract.md
    if [ -d apps/site ]; then pnpm --filter site build; else echo "build-site: apps/site ещё нет (PR #16), сборка не запускается"; fi

# Резервная копия наблюдаемости (issue #14, этап 0.2). НЕ входит в verify:
# это операция на VPS, а не проверка чистого checkout.
backup-obs:
    ./scripts/backup-observability.sh

# Восстановление по UTC-префиксу: just restore-obs 20261125T120000Z
# Деструктивно — требуется CONFIRM=1 (см. docs/runbook.md).
restore-obs prefix:
    ./scripts/restore-observability.sh "{{prefix}}"

# Безопасная репетиция backup/restore во временном каталоге (DRY_RUN=1).
backup-drill:
    ./scripts/backup-drill.sh

# Необязательная фиксация инструментов: mise подхватит версии из mise.toml,
# если он установлен; иначе просто печатает инструкцию. Никого не заставляем.
bootstrap:
    #!/usr/bin/env bash
    set -euo pipefail
    if command -v mise >/dev/null 2>&1; then
        mise install
    else
        echo "mise не найден: инструменты зафиксированы в mise.toml, установите mise или используйте свои версии"
    fi
    pnpm install --frozen-lockfile
    uv sync --frozen
    echo "bootstrap: зависимости готовы"

# Локальная проверка уже поднятого контура (только чтение, ничего не запускает).
obs-health:
    ./scripts/obs-health.sh

# Репетиция алертов: статическая проверка + тестовая запись в Loki, если он поднят.
alert-drill:
    python3 scripts/alert-drill.py

# Подготовка keyless-подписи артефакта; НЕ входит в verify и CI.
sign-artifact path:
    ./scripts/sign-artifact.sh "{{path}}"

# Локальный просмотр документации MkDocs (публикация всё ещё под ENABLE_DOCS_PAGES).
docs-serve:
    uvx --from mkdocs-material==9.8.2 mkdocs serve
