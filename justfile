# Единая точка входа для локальных проверок и CI (ADR 0007, issue #26).
# Вызов: just <recipe>. Список: just --list.
set shell := ["bash", "-uc"]

# Всё сразу: то, что обязательно в CI.
verify: check lint config-lint workflows-lint secrets test build-site
    @echo "just verify: все проверки пройдены"

# Документация, ADR, ссылки, CODEOWNERS и шаблонные секреты.
check:
    python3 scripts/check.py

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

# Тесты доступных компонентов.
test: test-web
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
