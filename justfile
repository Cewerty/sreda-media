# Единая точка входа для локальных проверок и CI (ADR 0007, issue #26).
# Вызов: just <recipe>. Список: just --list.
set shell := ["bash", "-uc"]

# Всё сразу: то, что обязательно в CI.
verify: check lint config-lint workflows-lint secrets test
    @echo "just verify: все проверки пройдены"

# Документация, ADR, ссылки, CODEOWNERS и шаблонные секреты.
check:
    python3 scripts/check.py

# Линтеры кода: Python (ruff) и JS/TS (Biome).
lint:
    uv run --project apps/cms-api ruff check apps/cms-api
    pnpm --filter @sreda/cms-web check

# Валидация конфигурационных файлов репозитория.
config-lint:
    python3 scripts/config_lint.py

# actionlint + zizmor для workflow-файлов.
workflows-lint:
    bash scripts/workflows_lint.sh

# gitleaks по всей истории репозитория (issue #13, замечание 2).
secrets:
    go install github.com/gitleaks/gitleaks/v8@v8.30.1
    "$(go env GOPATH)/bin/gitleaks" git --redact --no-banner

# Тесты доступных компонентов.
test:
    pnpm --filter @sreda/cms-web test
    # cms-api: тесты из PR #42 пока не в main (stacked PR на chore/27-cms-foundation-base).
    if [ -d apps/cms-api/tests ]; then uv run --project apps/cms-api python -m pytest apps/cms-api/tests -q; else echo "cms-api: тестов пока нет в main (PR #42)"; fi

# Покрытие: пока заглушка, чтобы не создавать иллюзию полноценного прогона.
cov: test
    @echo "cov: отчёт по покрытию ещё не настроен (issue #26)"

# Сборка сайта: apps/site появится после PR #16, пока проверяем контракт.
build-site:
    test -f docs/adr/0014-cross-stack-content-contract.md
    @echo "build-site: apps/site ещё нет (PR #16), сборка не запускается"
