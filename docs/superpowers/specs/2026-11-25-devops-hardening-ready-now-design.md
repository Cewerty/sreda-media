# Design: DevOps hardening — Ready now

- **Статус:** одобрено пользователем 25.11.2026, реализация не начиналась.
- **Ветка:** `observability/foundation`.
- **Автор:** Костян (Zisvit), DevOps.
- **Смежный документ:** `2026-11-25-devops-hardening-after-address-design.md`.

## 1. Контекст и ограничения

В ветке уже лежат обязательный статус `ci`, observability-стек, backup/restore,
Uptime Kuma как код, deploy/smoke/сверка артефакта, coverage и drills. Новые
изменения должны готовить инфраструктуру, а не включать её.

Жёсткие ограничения:

- `serv` — личный сервер пользователя, не используется и не трогается;
- новый PR не создаётся, работа продолжается в `observability/foundation`;
- чужие PR и ветки, особенно PR #16, не трогаются;
- версия Ильи (`check_log_schema.py`, `justfile`, `ci.yml`, `CONTRIBUTING.md`) авторитетна;
- коммиты — conventional commits с подробным телом;
- секреты хранятся только вне репозитория.

## 2. Цели и границы

Цели: подготовить конфигурацию хоста, зафиксировать SLO и DR-параметры,
уменьшить рутину локальной диагностики и сделать проверки политик read-only.

Вне границ: выкладка, включение алертов, покупка второго провайдера мониторинга,
изменение branch protection rules, работа с `serv`, изменение `apps/site`.

## 3. Архитектура

Четыре независимых модуля с общим принципом: «источник правды в репозитории →
детерминированный проверщик → сообщение в `just verify` или отдельный workflow».

```text
docs/slo.md + deploy/observability/slo.json
        └── scripts/check_slo.py ──> verify
deploy/host/*.template
        └── scripts/check_host_config.py ──> verify
docs/*.md + justfile + scripts/*
        └── scripts/check_runbook_commands.py ──> verify
.github/workflows/*.yml
        └── scripts/audit_workflows.py ──> verify
GitHub branch protection (read-only)
        └── scripts/check_branch_policy.py ──> policy-check.yml
```

Каждый модуль можно проверять и откатывать отдельно; модули не зависят друг от
друга по данным.

## 4. Компоненты

### 4.1 Host config как код

Новые файлы:

- `deploy/host/Caddyfile.template` — конфиг витрины с плейсхолдером
  `{{SREDA_SITE_URL}}`, без секретов и без реального домена;
- `deploy/host/docker-daemon.json.template` — `log-opts` с `max-size` и
  `max-file`, чтобы docker-логи не заполняли диск;
- `deploy/host/journald-vacuum.service` и `deploy/host/journald-vacuum.timer`
  — ограничение размера journald;
- `scripts/check_host_config.py`, рецепт `just check-host-config`.

Проверщик: `caddy validate` для шаблона (с подстановкой временного значения),
`systemd-analyze verify` для юнитов, `json.loads` для daemon-шаблона. При
отсутствии `caddy` или `systemd-analyze`соответствующий шаг честно пропускается с
сообщением; реальная синтаксическая ошибка — `exit 1`.

### 4.2 SLO и DR

Новые файлы:

- `docs/slo.md` — SLI (доступность, p95-латентность, свежесть бэкапа), SLO 99%
  доступности в месяц, error budget, RTO 15 минут, RPO 24 часа;
- `deploy/observability/slo.json` — машиночитаемый источник правды с порогами
  и UID'ами дашборда/правил;
- `deploy/observability/grafana-dashboards/slo.json` — панели доступности,
  латентности, свежести бэкапа и остатка error budget;
- дополнение `grafana-provisioning/alerting/rules.yml` — правила burn-rate и
  «бэкап старше 24 часов», все с `enabled="false"`;
- `scripts/check_slo.py`, `scripts/dr-drill.sh`, рецепты `just check-slo` и
  `just dr-drill`.

`check_slo.py` сверяет числа в `docs/slo.md`, `slo.json`, дашборде и правилах;
обязательно проверяет, что новые правила выключены. `dr-drill.sh` работает во
временном каталоге: проверяет наличие `backup.service`, `backup.timer`,
`backup-observability.sh`, `restore-observability.sh`, guard `CONFIRM=1` и
совпадение расписания с RPO из `slo.json`.

Существующий `loki-config.yml` уже имеет `retention_period: 720h`, а
`grafana-dashboards/overview.json` уже существует — оба файла не дублируются.

### 4.3 DX

Новые файлы:

- `scripts/doctor.sh`, рецепт `just doctor` — таблица инструментов и версий;
  всегда возвращает 0, опциональный режим `--strict` не используется;
- `scripts/check_runbook_commands.py`, рецепт `just check-runbook` —
  разбирает bash-блоки в `docs/*.md`, извлекает `just <recipe>` и
  `scripts/*.sh|py`, сверяет с `justfile` и файловой системой;
- `scripts/audit_workflows.py`, рецепт `just audit-workflows` — каждая внешняя
  `uses:` обязана иметь 40-символьный SHA; локальные `./...` разрешены.

Проверщики игнорируют комментарии и строки с плейсхолдерами; расхождение — `exit 1`.

### 4.4 Read-only политика

Новые файлы:

- `scripts/check_branch_policy.py`, рецепт `just check-github-policy`;
- `.github/workflows/policy-check.yml` (`workflow_dispatch` + еженедельный cron,
  `permissions: contents: read`, `GH_TOKEN: ${{ github.token }}`).

Скрипт читает `GET /repos/{owner}/{repo}/branches/main/protection` через `gh api`
и проверяет `required_status_checks.strict == true`, наличие `ci` в контекстах и
`required_approving_review_count >= 1`. Только чтение: никаких PUT/PATCH.
Локально при отсутствии `gh` — пропуск.

## 5. Поток данных и обработка ошибок

1. Источник правды — текст или JSON в репозитории.
2. Проверщик читает его и сравнивает с артефактами (дашборд, правила, justfile).
3. При отсутствии внешнего инструмента шаг пропускается с явным сообщением.
4. При расхождении проверщик печатает конкретный файл и строку и возвращает 1.
5. Новые рецепты добавляются в `verify`; `policy-check.yml` остаётся вне
   обязательного статуса `ci` и не меняет ruleset.

## 6. Интеграция и документация

- `justfile`: `check-host-config`, `check-slo`, `check-runbook`,
  `audit-workflows` в `verify`; `doctor`, `dr-drill`, `check-github-policy` —
  отдельные рецепты.
- `CONTRIBUTING.md` и `docs/DEVOPS-STATUS.md`: новые команды и граница «готово,
  но не включено».
- `mkdocs.yml`: две spec-страницы в разделе «Решения и спецификации».
- Ничего не меняет `ci.yml`, `check_log_schema.py`, файлы PR #16 и `serv`.

## 7. Тестирование и критерии приёмки

Проверки до коммита: `bash -n`, `py_compile`, `scripts/check.py`,
`scripts/config_lint.py`, `actionlint`, `zizmor`, `mkdocs build --strict`,
полный `just verify` с локальным PostgreSQL на `127.0.0.1:55432`.

Позитивные сценарии: новые проверщики проходят на 현재 дереве; `doctor`
печатает таблицу и возвращает 0; `dr-drill` не трогает `/srv` и systemd.
Негативные сценарии: временная порча `slo.json`, удаление SHA у `uses:`,
ссылка на несуществующий `just`-рецепт в doc — каждый проверщик должен упасть
с внятным сообщением.

Критерий приёмки: `just verify` зёленый, правила с `enabled="false"`, новый PR
не создан, `serv` не затронут.
