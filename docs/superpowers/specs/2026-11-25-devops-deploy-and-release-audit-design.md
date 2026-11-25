# DevOps: репетиция выкладки и аудит релизного цикла

**Статус:** Approved 25.11.2026  
**Ветка:** `observability/foundation`  
**Ответственный:** Костян (Zisvit), DevOps

## Контекст и цель

Большинство DevOps-проверок уже вынесено в `just verify`, но три пути остаются непокрытыми автоматически: атомарная выкладка и откат через `scripts/deploy-static.sh`, корректность сгенерированного `release.json` и читаемость структурированных логов для дежурного. Цель — добавить read-only проверки и безопасные репетиции во временных каталогах, не меняя прод-контур и не включая отложенные гейты.

## Вне границ

- Выкладка на `serv`, изменение `/srv/sreda`, systemd, Caddy и Docker на сервере.
- Включение `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL` и правил алертов.
- Изменение `apps/site`, PR #16, прав чужих веток и PR, создание нового PR.
- Изменение `ci.yml` и `scripts/check_log_schema.py` — версия Ильи авторитетна.
- Установка хуков git, изменение настроек GitHub, раскрытие секретов.
- Dependabot/Renovate и Kafka.

## Архитектура

Каждый модуль — отдельный проверщик с одним входом: опциональный корень репозитория через `argv[1]` для негативных сценариев. Успех печатает одну строку `ok: ...` и возвращает 0. Ошибка проверки печатает `FAIL: ...` в stderr и возвращает 1. Отсутствие внешнего инструмента или необязательного артефакта — `SKIP: ...` и 0. Новые рецепты добавлены в `justfile`; проверки, работающие только с репозиторием, входят в `verify`, отчёты — вне него.

## Модуль 1. Репетиция выкладки и отката

**Файлы:** `scripts/deploy-drill.sh`, рецепт `just deploy-drill` в `verify`.

`scripts/deploy-drill.sh`:

1. Создаёт `tmp=$(mktemp -d)` и регистрирует `trap 'rm -rf "$tmp"' EXIT`.
2. В `$tmp/artifact` пишет `index.html` с маркером `Sreda Media drill` и `404.html`.
3. Вызывает `scripts/deploy-static.sh deploy "$tmp/artifact" "$tmp/releases" "$tmp/current"`.
4. Проверяет, что `$tmp/current` — симлинк на каталог внутри `$tmp/releases`, в нём есть `index.html` и `404.html`, а `$tmp/releases/.previous` содержит пустую строку (первый релиз).
5. Повторяет deploy со вторым артефактом с другим маркером; проверяет, что `.previous` указывает на первый релиз.
6. Вызывает `scripts/deploy-static.sh rollback "$tmp/releases" "$tmp/current"`; проверяет, что `$tmp/current` снова указывает на первый релиз и маркер в нём прежний.
7. Печатает `ok: deploy drill — выкладка, симлинк и откат в temporary root`.

Негативные сценарии через `SREDA_DRILL_ROOT` или `argv[1]`: артефакт без `404.html` приводит к `FAIL` и коду 1 до создания релиза; rollback без `.previous` тоже даёт код 1. Скрипт не вызывает подкоманду `verify` (там нужен curl) и не обращается к `/srv/sreda`, `systemctl` или реальному `current`.

## Модуль 2. Аудит релизного цикла

**Файлы:** `scripts/check_release_manifest.py`, `scripts/pr_readiness.py`, рецепты `just check-release-manifest` (в `verify`) и `just pr-readiness <number>` (вне verify).

`scripts/check_release_manifest.py`:

- Принимает опциональный путь к `release.json`, по умолчанию `dist/release.json`. Если файла нет — `SKIP: release.json не найден`, код 0.
- Обязательные ключи: `generated_at`, `git_sha`, `git_branch`, `artifact_sha256`, `cosign_verified`, `operator`, `gates`.
- `generated_at` — ISO-строка, заканчивается на `Z`; `git_sha` — ровно 40 шестнадцатеричных символов и совпадает с `git rev-parse HEAD`; `artifact_sha256` — ровно 64 шестнадцатеричных символа.
- `cosign_verified` и четыре значения `gates` (`ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL`) — булевы; `operator` — непустая строка.
- Если рядом есть `artifact.sha256`, его хэш должен совпадать с `artifact_sha256`.
- Успех: `ok: release manifest — схема, git_sha и artifact_sha256 согласованы`.

`scripts/pr_readiness.py <number>`:

- Только read-only `gh pr view <number> --json number,title,state,mergeable,reviewDecision,statusCheckRollup,headRefName,baseRefName,author`.
- Печатает компактную таблицу: номер, state, mergeable, reviewDecision, итог statusCheckRollup, ветки и автора. Ничего не меняет в GitHub.
- Без `gh` или при ошибке доступа — `SKIP: gh недоступен`, код 0. Не ищет конкретный PR по умолчанию: номер обязан быть передан явно, чтобы не трогать чужие карточки автоматически.

## Модуль 3. Готовность метрик и алертов

**Файлы:** `deploy/observability/resource-limits.yml.template`, `scripts/check_external_probe.py`, `scripts/check_resource_budget.py`, рецепты `just check-external-probe` и `just check-resource-budget` в `verify`.

`scripts/check_external_probe.py` читает `deploy/observability/prometheus-external.yml.template`, `deploy/observability/blackbox.yml` и `deploy/observability/prometheus.yml`:

- В шаблоне должен быть job `sreda-external` с `metrics_path: /probe`, `params.module: ["http_2xx"]`, `params.target: ["${SREDA_SITE_URL}"]` и relabel-подстановкой `target_label: __address__` на blackbox exporter.
- В `blackbox.yml` должен существовать модуль `http_2xx`.
- В рабочем `prometheus.yml` не должно быть job `sreda-external` — внешняя проба остаётся выключенной до адреса.
- Успех: `ok: external probe — шаблон готов, в рабочем конфиге проба не включена`.

`deploy/observability/resource-limits.yml.template` содержит шаблон лимитов для `grafana`, `loki`, `prometheus`, `node-exporter`, `blackbox-exporter` в формате `deploy.resources.limits.cpus`/`memory`, без привязки к рабочему compose. `scripts/check_resource_budget.py` сверяет, что `docs/resource-budget.md` содержит бюджет 500 ₽/мес, 20% RAM и ссылку на ADR 0006 §4, а шаблон содержит все пять сервисов и числовые лимиты. Успех: `ok: resource budget — лимиты подготовлены, в compose не применены`.

## Модуль 4. Кулинария структурированных логов

**Файлы:** `docs/log-queries.md`, `scripts/check_log_queries.py`, рецепт `just check-log-queries` в `verify`.

`docs/log-queries.md` содержит короткие LogQL-запросы для дежурного: поиск по `event`, `component`, `operation`, `outcome`, `correlation_id`, `status_code`, `elapsed_ms`; подсчёт ошибок по компоненту; выборка медленных запросов по `elapsed_ms`. Документ явно ссылается на ADR 0005 и `docs/slo.md`.

`scripts/check_log_queries.py`:

- Ищет в документе блоки кода с языком `logql`.
- Разрешённые поля: `event`, `component`, `operation`, `outcome`, `correlation_id`, `status_code`, `elapsed_ms`, `timestamp`, `environment`, `release`, `level`.
- Каждый запрос должен содержать хотя бы одно разрешённое поле и не содержать `debug`, `request.body`, `raw_body`, `body=~`.
- Документ должен упоминать `ADR 0005` и `docs/slo.md`.
- Успех: `ok: log queries — N запросов, только контрактные поля`.

## Интеграция в justfile

- `verify` дополняется в порядке: `check-host-config`, ..., `deploy-drill`, ..., `config-lint`, `check-env-contract`, `check-ports`, `check-image-pins`, `check-ops-policy`, `check-release-manifest`, `check-external-probe`, `check-resource-budget`, `check-log-queries`, `workflows-lint`, ...
- Отдельные рецепты: `pr-readiness <number>` и `check-ports` уже есть; новые `deploy-drill`, `check-release-manifest`, `pr-readiness`, `check-external-probe`, `check-resource-budget`, `check-log-queries` добавляются рядом с существующими проверками.
- `CONTRIBUTING.md` и `docs/DEVOPS-STATUS.md` получают по одной строке на каждую новую проверку; `mkdocs.yml` добавляет `docs/log-queries.md` в раздел «Эксплуатация».

## Тестирование

- `python3 -m py_compile` на новых `.py`; `bash -n` на `deploy-drill.sh`.
- Позитив: `deploy-drill.sh`, `check_release_manifest.py` на temp-манифесте, `pr_readiness.py` с несуществующим номером (SKIP), `check_external_probe.py`, `check_resource_budget.py`, `check_log_queries.py`.
- Негативы: битый артефакт без `404.html`; rollback без `.previous`; `release.json` с коротким `git_sha`; шаблон внешнего job с `sreda-external`, добавленный в рабочий `prometheus.yml`; LogQL-запрос с `request.body`. Каждый должен дать код 1.
- Общие проверки: `scripts/check.py`, `scripts/config_lint.py`, `scripts/check_links.py`, `scripts/check_runbook_commands.py`, `scripts/audit_workflows.py`, `actionlint`, `zizmor`, `mkdocs build --strict`, `git diff --check`.
- Полный `just verify` с PostgreSQL 18 на `127.0.0.1:55432`; лог `/tmp/opencode/just-verify-deploy-release-audit.log`.
- Финальная сверка: `ENABLE_*` не заданы, все правила в `rules.yml` остаются `enabled: "false"`, PR #16 OPEN, дерево чистое, HEAD == remote.

## Коммиты

1. `chore(devops): rehearse deploy and rollback in temporary root` — `scripts/deploy-drill.sh`, justfile, рецепт в verify.
2. `chore(devops): audit release manifest and PR metadata` — два скрипта, рецепты.
3. `chore(devops): prepare metric and budget checks` — шаблон лимитов, два проверщика, рецепты.
4. `docs(devops): add log query cookbook and checker` — `docs/log-queries.md`, проверщик, рецепт, документация.
5. Финальный коммит документации после верификации.

Push — один раз в конце, в ветку `observability/foundation`, новый PR не создаётся.
