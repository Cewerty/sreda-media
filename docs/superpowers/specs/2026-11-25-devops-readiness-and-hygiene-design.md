# DevOps readiness and hygiene — дизайн

> **Статус:** Approved 25.11.2026
> **Реализация:** не начиналась
> **Ветка:** `observability/foundation`
> **Основание:** issue #9, #14, #26, #35; ADR 0005, ADR 0006 §4, ADR 0015

## Контекст и цель

К настоящему моменту в ветке подготовлены CI-гейты, observability, SLO/DR, deploy-заготовки, gated-проверки и обширная документация. Разрозненные проверки уже зелёные, но ответ на вопрос «готовы ли мы к выкладке?» требует вручную собирать факты из десятка файлов. Цель — свести готовность и гигиену конфигурации к небольшим read-only скриптам с предсказуемым выводом, не включая ничего в прод.

## Ограничения

- `serv` не используется; реальные сервисы не запускаются и не перезапускаются.
- Новый PR, новые ветки и worktree не создаются; PR #16 и чужие ветки не трогаются.
- Версия Ильи авторитетна: `check_log_schema.py`, `justfile`, `ci.yml`, `CONTRIBUTING.md` не переписываются «под себя»; новые проверки добавляются рядом.
- Коммиты только с подробными телами; вся контекстная информация остаётся в коммите.
- Секреты внутри репозитория не печатаются и не раскрываются.
- Принцип сохраняется: готовим заранее, включаем только когда объект и адрес существуют.
- Не добавляются Dependabot/Renovate, Kafka и обязательная подпись коммитов.

## Архитектура

Один шаблон для всех модулей: источник правды в репозитории (или read-only `gh`) → проверяющий скрипт → табличный вывод в stdout → рецепт `just`. Скрипты не меняют файлы, не задают env, не вызывают деплой и не включают алерты. Каждый скрипт принимает необязательный первый аргумент с корнем репозитория — это позволяет проверять негативные сценарии на временной копии, не затрагивая рабочее дерево.

Коды завершения: `0` — проверка выполнена, в том числе нормальный вердикт `NO-GO` или `SKIP`; `1` — только реальная ошибка проверки (некорректный вход,отсутствующий обязательный файл, нарушение контракта). Readiness и мета-линт запускаются вручную; гигиена конфигурации и операционная политика входят в `just verify` сразу после `config-lint`.

## Модуль 1: Go/No-Go readiness как код

**Файлы:** `scripts/release_readiness.py`, рецепт `release-readiness` в `justfile` (вне `verify`).

Скрипт собирает таблицу в формате «проверка | состояние | комментарий» и печатает итог `READY`, `NO-GO` или `SKIP`. Итог `READY` возможен только если все критичные строки зелёные; нормальное отсутствие артефакта или незаданный адрес даёт `NO-GO` с пояснением, а не падение.

Состав таблицы:

- `git` — HEAD, ветка, чистота рабочего дерева (`git status --porcelain` только чтение).
- Артефакт — наличие `dist/index.html`, `dist/404.html`, `dist/artifact.tar.gz`, `dist/artifact.sha256`, опционально `dist/cosign.sig` и `dist/cosign.pem`.
- Флаги — значения `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL` из окружения; значения секретов не печатаются.
- Алерты — количество правил в `deploy/observability/grafana-provisioning/alerting/rules.yml`, все ли `labels.enabled == "false"`.
- PR #16 — `gh pr view 16 --json state,mergeable` в режиме только чтения; при отсутствии `gh` или сети строка получает `SKIP`, итог не может быть `READY`.
- Документы — наличие `docs/DEVOPS-STATUS.md`, `docs/runbook.md`, `docs/slo.md`, `docs/resource-budget.md`.
- QA-адрес — заполненность `SREDA_SITE_URL` и отсутствие тестового домена в репозитории.

`SKIP` используется, когда проверка принципиально недоступна в текущем окружении (нет `gh`, нет сети). Скрипт ничего не включает и не меняет, в том числе не трогает настройки GitHub.

## Модуль 2: Гигиена конфигурации

**Файлы:** `scripts/check_env_contract.py`, `scripts/check_ports.py`, `scripts/check_image_pins.py`, рецепты `check-env-contract`, `check-ports`, `check-image-pins` внутри `verify` после `config-lint`.

`check_env_contract.py` собирает плейсхолдеры вида `${VAR}` из `deploy/`, `.github/`, `scripts/` и `justfile`. Переменная считается известной, если её имя есть в `deploy/observability/.env.example`, `apps/cms-api/.env.example` или явно перечислено в документе `docs/SECRET-ROTATION.md`. Локальные shell-переменные `PREFIX`, `RETENTION_DAYS`, `TS`, `SQL_FILE`, `GRAFANA_FILE` заносятся в явный список исключений с пояснением в коде. Значения переменных и секреты никогда не печатаются — только имена.

`check_ports.py` сверяет карту портов: dev — PostgreSQL `55432`, Grafana `13000`, Loki `13100`, Alloy `13345`; prod — Grafana `3000`, Loki `3100`, Alloy `12345`, Prometheus `9090`, node_exporter `9100`, blackbox_exporter `9115`, PostgreSQL `5432`, GlitchTip `8000`, Uptime Kuma `3001`. Проверяются отсутствие коллизий и то, что все публикуемые наружу порты привязаны к `127.0.0.1`. Источник — compose-файлы в `deploy/`; ожидаемая карта объявлена в скрипте как константа.

`check_image_pins.py` проверяет строки `image:` в `deploy/**/*.yml`: образ должен иметь фиксированный тег или digest; `latest` запрещён. Единственное документированное исключение — `glitchtip/glitchtip:latest` в профиле `errors`, пока не выбран проверенный релиз GLITCHTIP_IMAGE. Исключение фиксируется константой в скрипте и поясняется в `docs/DEVOPS-STATUS.md`.

## Модуль 3: Операционная политика

**Файлы:** `scripts/check_ops_policy.py`, `docs/resource-budget.md`, рецепт `check-ops-policy` внутри `verify` рядом с проверками гигиены; ссылки на новый документ в `docs/DEVOPS-STATUS.md` и `mkdocs.yml`.

Три независимых блока проверки:

1. **Backup.** `deploy/observability/backup.timer` содержит `OnCalendar=daily`; `deploy/observability/slo.json` задаёт свежесть бэкапа `24` часа; `scripts/restore-observability.sh` содержит guard `CONFIRM=1`; `deploy/observability/.env.example` объявляет имена age-переменных; сценарии бэкапа создают манифест SHA256; правило `sreda-backup-stale` остаётся `enabled=false`.
2. **Ресурсный gate.** `docs/resource-budget.md` существует и явно фиксирует бюджет около 500 ₽/месяц, запас не менее 20% RAM, требование измерить idle/peak и ссылку на ADR 0006 §4. Метричные сервисы остаются под `--profile logs`; включение без решения Ильи недопустимо. Перекрёстная проверка с `check_prometheus_profiles.py` допустима, но дублирования конфигурации не создаём.
3. **Логирование.** Значение по умолчанию `LOG_LEVEL=INFO`; в проде нет `DEBUG` по умолчанию и нет флагов захвата raw request/response body. Авторитетным контрактом остаётся `scripts/check_log_schema.py`; новая проверка только подтверждает дефолты окружения и не заменяет его.

`docs/resource-budget.md` — человекочитаемая политика: таблица текущих ограничений, порядок измерения, кто принимает решение о включении метрик и GLITCHTIP, ссылки на ADR 0005/0006.

## Модуль 4: Мета-линт процесса

**Файлы:** `scripts/check_commit_messages.py`, `scripts/check_issue_hygiene.py`, рецепты `check-commits` и `check-issues` вне `verify`.

`check_commit_messages.py` разбирает только коммиты ветки после `origin/main` (`git rev-list origin/main..HEAD`, только чтение). У каждого коммита проверяются: subject в формате conventional commit, непустое тело с контекстом и строка `Refs:`. Если `origin/main` недоступен — `SKIP`. Скрипт не меняет историю и не переписывает сообщения.

`check_issue_hygiene.py` запрашивает `gh issue list --state open --json number,title,labels,assignees,updatedAt` и печатает список открытых карточек без label/assignee или с давним обновлением (порог 30 дней). Никаких изменений в issue не производится; без `gh` или сети — `SKIP` с exit 0. Отчёт информационный и не является mandatory gate.

## Обработка ошибок и тестирование

Все скрипты пишут только в stdout/stderr, не сохраняют файлы и не меняют git. Ошибки ввода (пустой/битый YAML, отсутствующий обязательный файл) завершаются `exit 1` с понятным сообщением без traceback. Нормальное отсутствие артефакта, незаданный адрес или недоступный `gh` — это `NO-GO`/`SKIP` с `exit 0`.

Проверки реализации: `py_compile` для Python-скриптов; позитивные прогоны всех рецептов; негативные сценарии на временной копии (неизвестный `${VAR}`, коллизия портов, образ `latest` без исключения, сломанный backup-контракт, коммит без тела, issue без label); `scripts/check.py`, `scripts/config_lint.py`, `scripts/check_links.py`, `scripts/check_runbook_commands.py`, `scripts/audit_workflows.py`, `actionlint`, `zizmor`, `mkdocs build --strict`; полный `just verify` с PostgreSQL 18 на `127.0.0.1:55432`. Новые workflow не добавляются.

## Вне границ

- Реальная выкладка, включение `ENABLE_*`, SREDA_SITE_URL, алертов и внешних мониторов.
- Изменение настроек GitHub, комментариев в чужих issue и PR #16.
- `apps/site`, `serv`, `ci.yml`, `check_log_schema.py`.
- Dependabot/Renovate, Kafka, обязательная подпись коммитов.
