# Единая точка входа для локальных проверок и CI (ADR 0007, issue #26).
# Вызов: just <recipe>. Список: just --list.
set shell := ["bash", "-uc"]

# Всё сразу: то, что обязательно в CI. Версия Ильи из PR #45 — авторитетная.
verify: check check-logs check-alerts check-alert-runbooks check-uptime check-host-config check-slo check-runbook audit-workflows docs-build install lint-web types test-web build-web api-check config-lint check-env-contract check-ports check-image-pins check-ops-policy workflows-lint audit-hardening secrets build-site
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

# Runbook-ссылки алертов: у каждого правила есть якорь в docs/runbook.md.
check-alert-runbooks:
    uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py

# Конфигурация Uptime Kuma как код: мониторы 200/404, Telegram, интервал >=30.
check-uptime:
    python3 scripts/check_uptime_config.py

# Хостовые шаблоны Caddy/Docker/journald как код.
check-host-config:
    python3 scripts/check_host_config.py

# Read-only контракт переменных окружения: только имена, без значений.
check-env-contract:
    python3 scripts/check_env_contract.py

# Read-only карта портов compose: без запуска сервисов.
check-ports:
    python3 scripts/check_ports.py

# Read-only проверка фиксации образов: latest запрещён.
check-image-pins:
    python3 scripts/check_image_pins.py

# Read-only политика: backup, ресурсный gate и дефолты логирования.
check-ops-policy:
    uv run --with pyyaml==6.0.4 python scripts/check_ops_policy.py

# Read-only сверка compose-профилей метрик и датасорса Grafana, без запуска сервисов.
logs-profile-check:
    uv run --with pyyaml==6.0.4 python scripts/check_prometheus_profiles.py

# Сверка SLO, дашборда и выключенных правил.
check-slo:
    uv run --with pyyaml==6.0.4 python scripts/check_slo.py

# DR-репетиция во временном каталоге, без /srv и systemd.
dr-drill:
    bash scripts/dr-drill.sh

# Диагностика инструментов: справка, всегда exit 0.
doctor:
    bash scripts/doctor.sh

# Проверка команд в bash-блоках документации.
check-runbook:
    python3 scripts/check_runbook_commands.py

# Аудит SHA-пинов внешних GitHub Actions.
audit-workflows:
    python3 scripts/audit_workflows.py

# Неблокирующий сбор coverage в coverage-reports/ с SHA256SUMS.
coverage: install
    bash scripts/collect_coverage.sh

# Ежедневная проверка относительных ссылок в docs/.
link-check:
    python3 scripts/check_links.py

# Политика безопасности workflow: права, checkout и run:.
audit-hardening:
    uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py

# MkDocs strict-сборка во временном каталоге, без публикации в Pages.
docs-build:
    bash scripts/docs-build.sh

# Smoke статической витрины: 200/404 и маркер контента (после адреса/Q-1).
smoke url:
    SREDA_SMOKE_MARKER="${SREDA_SMOKE_MARKER:-}" ./scripts/smoke-static.sh "{{url}}"

# Синтетическая проверка по SREDA_SITE_URL, не в verify.
synthetic:
    bash scripts/synthetic-check.sh

# Локальный предпрогон перед коммитом: только чтение, хуки не ставит.
pre-commit:
    bash scripts/pre-commit.sh

# Сверка подписи и хэша статического артефакта (не в verify/CI).
verify-artifact path:
    bash scripts/verify-artifact.sh "{{path}}"

# Манифест релиза как код; не входит в verify и CI.
release-manifest path:
    bash scripts/release-manifest.sh "{{path}}"

# Read-only отчёт о готовности к выкладке; ничего не включает и не публикует.
release-readiness:
    uv run --with pyyaml==6.0.4 python scripts/release_readiness.py

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

# Покрытие: реальный сбор через scripts/collect_coverage.sh, неблокирующе.
cov: coverage
    @echo "cov: отчёты собраны в coverage-reports/ (если плагины доступны)"

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

# Read-only проверка защиты main (требует gh и доступ).
check-github-policy:
    python3 scripts/check_branch_policy.py

# Read-only проверка новых коммитов: subject, тело и Refs.
check-commits:
    python3 scripts/check_commit_messages.py

# Read-only отчёт о гигиене открытых issue; ничего не меняет в GitHub.
check-issues:
    python3 scripts/check_issue_hygiene.py

# Учебный хаос-двойник: временный Compose-стек, без прода и алертов.
chaos-twin scenario:
    ./scripts/chaos-twin.sh "{{scenario}}"

# Все учебные сценарии подряд; вне verify и CI.
chaos-drill:
    #!/usr/bin/env bash
    set -euo pipefail
    for scenario in stop-loki disk-full stale-backup; do
        ./scripts/chaos-twin.sh "$scenario"
    done

# Демо-дайджест по фиксированным локальным событиям, без сети и секретов.
sre-digest:
    python3 scripts/log_digest.py

# Нормализация вывода Astro в корневой dist для подписи и выкладки.
stage-site:
    bash scripts/stage-site.sh

# Read-only проверка контракта артефакта; не входит в verify и ci.
check-site-artifact:
    python3 scripts/check_site_artifact.py

# Сквозная локальная репетиция выкладки, без прода и гейтов; вне verify и CI.
deploy-drill:
    ./scripts/deploy-drill.sh

# Аддитивный машиночитаемый контракт дриля; не входит в verify и CI.
emit-drill-contract drill-id artifact-sha:
    python3 scripts/emit_drill_contract.py "{{drill-id}}" --artifact-sha256 "{{artifact-sha}}" --checks "{{drill-id}}-checks.json" --out "{{drill-id}}-contract.json"

verify-drill-contract path:
    python3 scripts/verify_drill_contract.py "{{path}}"

# Канонический дайджест дерева: стабилен к mtime и порядку обхода.
canonical-tree-digest path:
    python3 scripts/canonical_tree_digest.py "{{path}}"

# Read-only защита ретенции: .last и минимальное число наборов не удаляются.
retention-guard path:
    python3 scripts/retention_guard.py "{{path}}"

# Self-test аддитивного слоя доказательств; без сети и без прода.
drill-contract-selftest:
    python3 scripts/test_drill_contract.py

# Read-only сравнение выданных байтов с ожидаемым SHA-256; вне verify и CI.
verify-served-bytes url expected-sha:
    python3 scripts/verify_served_bytes.py --url {{url}} --expected-sha256 {{expected-sha}}

# Read-only аудит закреплённых версий инструментов; вне verify и CI.
check-tool-pins:
    python3 scripts/check_tool_pins.py

# Единый аддитивный отчёт по пинам; вне verify и CI.
audit-pins-report:
    python3 scripts/audit_pins_report.py

# Read-only ресурсный гейт ADR 0006 §4; без ENABLE_* и без required status.
resource-gate:
    python3 scripts/resource_gate.py

# Read-only аудит завершённых backup-наборов; не удаляет и не восстанавливает.
audit-backups path:
    python3 scripts/audit_backups.py "{{path}}"

# Синтетическая репетиция restore во временном каталоге, без прода и БД Ильи.
restore-drill:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 scripts/restore_drill.py --artifact-sha256 "${SREDA_ARTIFACT_SHA256:-$(printf 'a%.0s' {1..64})}"

# Репетиция порядка ADR 0015; CMS-шаги честно помечены SKIP.
release-rehearsal:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "SKIP: migrate/seed — зона Ильи, ADR 0013/0015"
    ./scripts/stage-site.sh
    python3 scripts/check_site_artifact.py
    python3 scripts/backup_drill.py 2>/dev/null || echo "SKIP: backup-drill недоступен"
    ./scripts/deploy-drill.sh

# Report-only агрегатор доказательств дрилей; не входит в verify и ci.
drill-gate:
    python3 scripts/aggregate_drill_reports.py --summary --allow-missing

# Сравнение двух локальных деревьев по каноническому digest; только SIMULATED.
mirror-verify primary standby:
    python3 scripts/mirror_verify.py "{{primary}}" "{{standby}}"

# Read-only проверка DRAFT-шаблонов топологии; без provisioning и DNS.
check-replica-templates:
    python3 scripts/check_replica_templates.py

# Report-only проверка timeout/concurrency вне ci.yml.
check-workflow-timeouts:
    uv run --with pyyaml==6.0.4 python scripts/check_workflow_timeouts.py
