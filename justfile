# Единая точка входа для локальных проверок и CI (ADR 0007, issue #26).
# Вызов: just <recipe>. Список: just --list.
set shell := ["bash", "-uc"]

# Всё сразу: то, что обязательно в CI.
verify: check check-logs install lint types test build-web api-check config-lint workflows-lint secrets build-site
    @echo "just verify: все проверки пройдены"

# Зависимости чистого checkout (pnpm workspaces + uv workspace).
install:
    pnpm install --frozen-lockfile
    uv sync --frozen

# Полный quality gate CMS API из apps/cms-api/justfile (PR #45).
# Пока вложенный justfile не в main, выполняется базовый ruff/pytest без иллюзии полного прогона.
api-env: install
    if [ ! -f apps/cms-api/.env ] && [ -f apps/cms-api/.env.example ]; then cp apps/cms-api/.env.example apps/cms-api/.env; fi

api-check: api-env
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -f apps/cms-api/justfile ]; then
        cd apps/cms-api && UV_NO_SYNC=1 just check
    else
        echo "cms-api: вложенный justfile появится после PR #45; выполняется базовый прогон"
        uv run --project apps/cms-api ruff check apps/cms-api
        if [ -d apps/cms-api/tests ]; then
            uv run --project apps/cms-api python -m pytest apps/cms-api/tests -q
        else
            echo "cms-api: тестов пока нет в main (PR #42)"
        fi
    fi

# Документация, ADR, ссылки, CODEOWNERS и шаблонные секреты.
check:
    python3 scripts/check.py

# Контракт структурированных логов ADR 0005: обязательные поля и отсутствие PII.
check-logs:
    python3 scripts/check_log_schema.py

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
