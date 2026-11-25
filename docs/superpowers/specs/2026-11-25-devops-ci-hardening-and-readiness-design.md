# DevOps: защита CI и операционная готовность — дизайн

**Статус:** одобрено пользователем 25.11.2026.  
**Ветка:** `observability/foundation`.  
**Обновлено:** 25.11.2026.  
**Ответственный:** Костян (Zisvit), DevOps.

## 1. Контекст и цель

В ветке уже реализованы два ранее одобренных плана: хостовые шаблоны, SLO/DR,
DX-проверщики, read-only проверка политики ветки, gated synthetic,
gated provenance и gated-дашборд. Новый этап закрывает три оставшихся пробела,
которые не требуют адреса/Q-1 и не включают никаких прод-гейтов:

1. Политика безопасности workflow должна быть проверяемой локально, а не только
   через zizmor.
2. У алертов нет ссылок на процедуру реагирования; нет шаблона разбора инцидента
   и памятки по ротации age-ключа бэкапов.
3. Нет машиночитаемой записи о том, что именно было собрано и подписано: манифест
   релиза как код.

Цель: подготовить проверки и документы, не меняя обязательный статус `ci`,
не включая алерты, выкладку, Pages или provenance и не заходя на `serv`.

## 2. Ограничения

- `serv` — личный сервер пользователя, не используется и не трогается.
- Новый PR не создаётся; работа продолжается только в `observability/foundation`.
- Чужие PR и ветки, особенно PR #16, не трогаются.
- Версия Ильи авторитетна: `check_log_schema.py`, `justfile`, `ci.yml` и
  `CONTRIBUTING.md` из PR #45 остаются без изменений по существу.
- Коммиты — conventional commits с подробным телом; контекст в коммите, не в PR.
- Секреты хранятся вне репозитория; в `.env.example` только имена переменных.
- Принцип «готовим заранее, включаем только когда объект и адрес существуют».
- Не добавляем Dependabot/Renovate, Kafka и обязательную подпись коммитов.

## 3. Вне границ

- Любая реальная выкладка, включение `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`,
  `ENABLE_PROVENANCE`, `SREDA_SITE_URL` и Telegram contact point.
- Перевод правил Grafana Alerting в `enabled: "true"`.
- Изменение настроек GitHub branch protection (только чтение уже есть).
- Изменение `apps/site`, PR #16, `ci.yml`, `check_log_schema.py`, `serv`.
- Создание второй ветки, worktree или PR.

## 4. Подпроект 1: проверка безопасности workflow

### Компоненты

- `scripts/check_workflow_hardening.py` — проверщик на stdlib + PyYAML.
- `just audit-hardening` — рецепт в `verify` сразу после `audit-workflows`.
- Неблокирующий негативный тест вручную: временная порча копии workflow.

### Источник правды и поток данных

Вход: все файлы `.github/workflows/*.yml`. Проверщик загружает их через
`yaml.safe_load` и собирает список ошибок. Выход: `ok:`-строка при успехе,
`FAIL:`-строки и exit 1 при нарушениях. Ничего не записывает в репозиторий.

### Правила

- У каждого workflow есть top-level `permissions`; `write-all` запрещён.
- `contents: read` присутствует в top-level `permissions`.
- Повышенные права разрешены только по списку:
  - `pull-requests: write` — только `auto-review.yml`;
  - `pull-requests: read` — только `dependency-review.yml`;
  - `id-token: write` и `attestations: write` — только `provenance.yml`;
  - job-level `pages: write` и `id-token: write` — только job `publish` в
    `docs-pages.yml`.
- `pull_request_target` не используется.
- Для каждого `actions/checkout` с PR-событиями задан
  `with.persist-credentials: false`.
- В скалярных значениях `run:` нет подстановок `${{ github.event.* }}`.

### Обработка ошибок

Отсутствие PyYAML, нечитаемый файл или невалидный YAML — exit 1. Отсутствие
каталога `.github/workflows` — exit 1. Ошибки накапливаются и печатаются списком,
чтобы было видно все нарушения за один прогон.

### Тестирование

- Позитив: `just audit-hardening` на текущих workflow — `ok`.
- Негатив: временная копия workflow с `permissions: write-all` и `${{ github.event.* }}`
  в `run:` — exit 1; оригинал восстанавливается.
- `py_compile`, `config_lint.py`, `actionlint`, `zizmor`.

## 5. Подпроект 2: операционная готовность

### Компоненты

- `deploy/observability/grafana-provisioning/alerting/rules.yml` — добавить
  `annotations.runbook_url` ко всем правилам.
- `docs/runbook.md` — явные HTML-якоря `<a id="<rule_uid>"></a>` и раздел о
  реагировании по каждому правилу.
- `scripts/check_alert_runbooks.py` — новый проверщик, рецепт
  `check-alert-runbooks` в `verify` рядом с `check-alerts`.
- `docs/incidents/template.md` — шаблон разбора инцидента.
- `docs/BACKUP-KEY-ROTATION.md` — порядок ротации age-ключа.
- `deploy/observability/.env.example` — только имена переменных
  `SREDA_BACKUP_AGE_RECIPIENT` и `SREDA_BACKUP_AGE_IDENTITY` комментариями.
- `docs/SECRET-ROTATION.md` — ссылка на новую памятку.
- `mkdocs.yml` — новые страницы в навигации.

### Поток данных

`check_slo.py` задаёт список `rule_uids` в `deploy/observability/slo.json`.
Проверщик читает `rules.yml`: каждое правило обязано иметь `runbook_url` вида
`https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#<rule_uid>`,
а в `docs/runbook.md` обязан существовать якорь с этим `rule_uid`. Дополнительно
проверяется, что все три `rule_uid` из `slo.json` присутствуют в `rules.yml`.
Правила остаются `enabled: "false"`.

### Обработка ошибок

Отсутствующий `runbook_url`, ссылка на несуществующий якорь, расхождение UID —
exit 1 с перечислением проблем. Невалидный YAML — exit 1. Проверщик не меняет
правила и не отправляет уведомления.

### Тестирование

- `just check-alert-runbooks` — ok на текущих 10 правилах.
- Негатив: временно убрать один `runbook_url` — exit 1; оригинал восстановить.
- `check.py`, `config_lint.py`, `check_alert_rules.py`, `check_slo.py`,
  `mkdocs build --strict`, grep на `enabled: "true"` — пусто.

## 6. Подпроект 3: манифест релиза

### Компоненты

- `scripts/release-manifest.sh` — executable, принимает каталог артефакта.
- `just release-manifest path` — рецепт вне `verify` и CI.

### Данные манифеста

`release.json` в каталоге артефакта содержит: `generated_at` (UTC), `git_sha`,
`git_branch`, `artifact_sha256` (из `artifact.sha256`), `cosign_verified`
(наличие `cosign.sig`/`cosign.pem` и доступность `cosign`), `gates` с флагами
`ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL`,
`operator` из `$USER`. Скрипт не подписывает, не выкладывает и не меняет
исходный артефакт, кроме добавления `release.json`.

### Обработка ошибок

Нет каталога артефакта или `artifact.sha256` — exit 1. Отсутствие cosign —
`cosign_verified: false`, не ошибка. Скрипт честно печатает, что манифест
подготовлен, но гейты выключены.

### Тестирование

- Локальный temp-каталог с `index.html`, `404.html`, `artifact.tar.gz`,
  `artifact.sha256`: манифест создаётся, `json.tool` проходит, `git_sha`
  совпадает с HEAD.
- `bash -n`, `check_runbook_commands.py`, `audit_workflows.py`, `check.py`.

## 7. Интеграция и порядок

1. Проверка workflow: `scripts/check_workflow_hardening.py` + рецепт в `verify`;
   коммит `feat(devops): add workflow hardening guard` с `Refs: #9 #26`.
2. Операционная готовность: rules/runbook/checker/incident template/age rotation;
   коммит `docs(devops): link alerts to runbooks and add ops templates` с
   `Refs: #9 #14`.
3. Манифест релиза: `scripts/release-manifest.sh` + рецепт; коммит
   `chore(devops): add gated release manifest` с `Refs: #9 #14`.
4. Синхронизация документации: `CONTRIBUTING.md`, `docs/DEVOPS-STATUS.md`,
   `mkdocs.yml`; коммит `docs: reflect workflow and ops hardening checks` с
   `Refs: #9 #14 #26 #35`.
5. Верификация: py_compile, bash -n, check.py, config_lint, actionlint, zizmor,
   audit_workflows, mkdocs strict, полный `just verify` с PostgreSQL 18 на
   `127.0.0.1:55432`, один push в `observability/foundation`.

## 8. Критерии приёмки

- `just verify` зелёный, включая три новые проверки.
- `audit_workflows.py` проходит после добавления workflow-проверщика.
- Все 10 правил алертов имеют `runbook_url` и остаются `enabled: "false"`.
- `grep -c 'enabled: "true"'` по `rules.yml` равен нулю.
- env `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`,
  `SREDA_SITE_URL` не выставлены; `gh variable list` пуст.
- Новый PR не создан; `serv`, PR #16 и чужие ветки не тронуты.
- Рабочее дерево чистое после финального push.
