# DevOps — текущий статус

> **Ветка:** `observability/foundation`  
> **Обновлено:** 25.11.2026  
> **Ответственный:** Костян (Zisvit), DevOps  
> **Принцип:** готовим заранее, включаем только когда объект и адрес существуют.

Эта страница — короткий срез последних DevOps-задач: что уже лежит в ветке, что
проверено, что намеренно выключено и где искать детали. Полные процедуры остаются
в [Runbook](runbook.md), [Мониторинге](monitoring.md) и
[DEPLOYMENT](DEPLOYMENT.md).

## Последние коммиты

| Коммит | Тема | Суть |
| --- | --- | --- |
| `b3651cc` | `chore(devops): add deploy gates and non-blocking CI drills` | Deploy workflow как код, smoke-проверка, периодические алерты, Docker lint, dependency review и OSV, MkDocs в `verify`. |
| `3c631b7` | `chore(devops): add local guards, caches and coverage drills` | Кеши инструментов, coverage, link checker, валидация Uptime Kuma, `pre-commit`, `verify-artifact`, ротация секретов. |
| `6a1f51c` | `chore(devops): add uptime kuma config and ci drills` | `monitors.json`, provision-скрипт, restore-drill, Lighthouse-заготовка, Trivy v0.35.0. |
| `386faa4` | `ci(devops): automate local API DB and scheduled drills` | Локальный PostgreSQL 18 на `55432`, ночной backup-drill, cosign, ежедневный `docs-check`. |

### Что сделано в `3c631b7`

- Кеш `actionlint`/`gitleaks` через `actions/cache@v4.2.0` — быстрее повторные прогоны.
- Неблокирующий coverage: `scripts/collect_coverage.sh` + workflow `coverage.yml`.
- Ежедневная проверка ссылок: `scripts/check_links.py` + `docs-links.yml`.
- Валидация конфигурации Uptime Kuma как кода: `scripts/check_uptime_config.py`, рецепт `check-uptime` внутри `verify`.
- Локальный `scripts/pre-commit.sh` и сверка артефакта `scripts/verify-artifact.sh`.
- Памятка [Ротация секретов](SECRET-ROTATION.md).

### Что сделано в `b3651cc`

- `.github/workflows/deploy.yml`: ручной выкладки с `dry_run=true` по умолчанию и guard `ENABLE_DEPLOY=true`.
- `scripts/smoke-static.sh`: главная `200`, несуществующая страница `404`, маркер контента.
- `scripts/sign-artifact.sh`: хэш создаётся всегда, cosign-подпись опциональна.
- `.github/workflows/alert-drill.yml`: еженедельная репетиция правил, алерты остаются выключенными.
- Docker lint в `supply-chain.yml`: `docker compose config` и hadolint v3.5.0.
- `.github/workflows/dependency-review.yml`: Dependency Review и OSV, оба неблокирующие.
- `docs-build` добавлен в `just verify`: MkDocs `--strict` во временном каталоге, без публикации.

## Карта проверок

| Проверка | Где запускается | Блокирует `ci`? | Комментарий |
| --- | --- | --- | --- |
| `ci` | `ci.yml`, PR и `push main` | Да | Единственный обязательный статус в ruleset. |
| `log-schema`, `workflows-lint`, `conventions`, `config-lint`, `secrets`, `tests`, `site-build`, `cms-api` | внутри `ci.yml` | Да | path-aware; пропуск допустим только если проверка не применима. |
| `check-uptime`, `check-alerts`, `docs-build` | `just verify` | Да | Локально и внутри обязательных job'ов. |
| `supply-chain`, `dependency-review`, `coverage`, `docs-links`, `backup-drill`, `alert-drill`, `lighthouse`, `restore-drill` | Отдельные workflow | Нет | `continue-on-error` или вне `needs` агрегатора. |
| `deploy.yml` | `workflow_dispatch` | Нет | Guard `ENABLE_DEPLOY`, `dry_run=true` по умолчанию. |
| `docs-pages.yml` | `workflow_dispatch` + ежедневный `docs-check` | Нет | Публикация только при `ENABLE_DOCS_PAGES=true`. |

## Новые проверки готового контура

| Проверка | Запуск | Суть |
| --- | --- | --- |
| `check-host-config` | `just verify` | Хостовые шаблоны Caddy/Docker/journald как код, без секретов и реального домена. |
| `check-slo` | `just verify` | Сверка `docs/slo.md`, `slo.json`, дашборда и выключенных правил алертов. |
| `check-runbook` | `just verify` | Команды `just` и `scripts/*` в bash-блоках `docs/*.md` сверены с репозиторием. |
| `audit-workflows` | `just verify` | SHA-пины внешних GitHub Actions в workflow. |
| `audit-hardening` | `just verify` (обязательно) | Права workflow, persist-credentials, отсутствие github.event.* в run:. |
| `check-alert-runbooks` | `just verify` (обязательно) | Каждое правило алерта ссылается на существующий якорь в runbook. |
| `stage-site` | Отдельно | Копирует `apps/site/dist` в корневой `dist`; саму сборку не меняет. |
| `check-site-artifact` | Gated deploy/provenance, отдельно | Проверяет `dist/index.html` и `dist/404.html`; 404 ждёт issue #5. |
| `doctor` | Отдельно | Справка по инструментам, всегда exit 0; ничего не включает. |
| `dr-drill` | Отдельно | DR-репетиция во временном каталоге, без `/srv` и systemd. |
| `check-github-policy` | Отдельно, read-only | Только чтение защиты `main`; GitHub не меняется. |
| `release-manifest` | Вручную, вне `verify` и CI | Манифест артефакта как код, без подписи и выкладки. |
| `check-env-contract` | `just verify` | Имена `${VAR}` сверены с шаблонами окружения, значения не печатаются. |
| `check-ports` | `just verify` | Карта портов dev/prod, только `127.0.0.1`, без коллизий. |
| `check-image-pins` | `just verify` | Образы зафиксированы; `latest` запрещён кроме GLITCHTIP. |
| `check-ops-policy` | `just verify` | Backup 24ч, ресурсный gate ADR 0006 §4, дефолты логирования. |
| `release-readiness` | Вручную, вне `verify` и CI | Таблица готовности с вердиктом `READY`/`NO-GO`; ничего не включает. |
| `check-commits` | Вручную, вне `verify` и CI | Subject, тело и `Refs:` новых коммитов. |
| `check-issues` | Вручную, вне `verify` и CI | Read-only отчёт о карточках без label/assignee и stale. |

Все проверки подготовлены, но ничего не включают в прод: правила алертов
остаются выключенными, выкладка и включение мониторов — отдельные решения после
адреса и PR #16. Хостовые шаблоны, SLO/DR, DX-утилиты и read-only политика
реализованы этим набором коммитов, поэтому в разделе «Идеи на потом» остались
только нереализованные пункты. SBOM уже загружается как артефакт в
`supply-chain.yml`; повторно добавлять его не нужно.

## Локальные команды

```bash
# Полная проверка чистого checkout (PostgreSQL поднимается отдельно)
just api-db-up
just verify
just api-db-down

# Точечные проверки
just check-logs          # контракт структурированных логов
just check-alerts        # Grafana provisioning, правила должны быть выключены
just check-uptime        # Uptime Kuma monitors.json
just link-check          # относительные ссылки в docs/
just docs-build          # mkdocs build --strict без публикации
just alert-drill         # статический контроль + тест в Loki, если он поднят
just backup-drill        # безопасная репетиция в DRY_RUN=1
just obs-health          # только чтение уже поднятого контура
just logs-profile-check  # profiles/logs и датасорс Grafana без запуска сервисов

# Артефакт static site
just build-site
just sign-artifact dist
just verify-artifact dist
just smoke https://sreda.sielom.ru   # только после Q-1
```

## Подготовлено, но не включено

| Что | Почему выключено | Как включить |
| --- | --- | --- |
| Реальная выкладка через `deploy.yml` | Нет сайта в `main` (PR #16) и финального адреса (Q-1) | `ENABLE_DEPLOY=true`, `dry_run=false`, `base_url` |
| Публикация MkDocs на GitHub Pages | Нужно решение по адресу и budgets | `ENABLE_DOCS_PAGES=true` + dispatch |
| Uptime Kuma мониторы | Предполагают существующий URL | Применить `scripts/provision-uptime-kuma.sh` после Q-1 |
| Правила Grafana Alerting | Не хотим алертов о несуществующем сайте | Заменить `labels.enabled` на `"true"` и задать Telegram env |
| Внешняя независимая точка проверки | Один VPS = одна точка отказа | Отдельный провайдер или сервис после решения Ильи |
| Реальный smoke и Lighthouse | Ждут `apps/site` и адрес | После слияния PR #16 и Q-1 |
| Keyless provenance | `workflow_dispatch` c guard `ENABLE_PROVENANCE`, включается решением по ADR 0006 | `ENABLE_PROVENANCE=true` + dispatch на main |
| Синтетическая проверка | Без `SREDA_SITE_URL` честно сообщает «проверка не настроена» | Задать `SREDA_SITE_URL` после Q-1 |
| Манифест релиза | Готов как рецепт, но не входит в CI | `just release-manifest dist` после появления артефакта |
| Отчёт `release-readiness` | Вердикт `NO-GO` — нормальное состояние до адреса Q-1: нет флагов, QA-адреса и подготовленного артефакта | После Q-1 и появления артефакта `just release-readiness` пересчитает таблицу и покажет `READY` |
| Prometheus, node_exporter и blackbox_exporter | Метричный контур под `--profile logs`; по умолчанию не поднимается | Только после ресурсного gate ADR 0006 §4, `docker compose --profile logs up -d` |
| Внешняя проба `sreda-external` | `job` лежит в шаблоне с `${SREDA_SITE_URL}` и не активен | После PR #16/Q-1: `envsubst` в `prometheus.yml` и перезапуск profiled-сервиса |

## Блокирующие зависимости

- **PR #16** — минимальный Astro-сайт уже в `main`; `build-site` собирает его, а `stage-site` подготавливает корневой `dist`.
- **Q-1 с Артёмом** — домен, DNS и тестовый адрес выкладки.
- **ENABLE_DEPLOY / ENABLE_DOCS_PAGES** — флаги включаются отдельно, не «по умолчанию».
- **ADR 0006** — финальное решение о хостинге остаётся за Ильёй; включение метрик (`--profile logs`) дополнительно ждёт ресурсного gate §4.
- **#14** — независимый мониторинг и уведомления после появления объекта наблюдения.

## Правила работы в этой ветке

1. `serv` — личный сервер пользователя, не используется и не трогается.
2. Новый PR не создаётся: работа продолжается в существующей ветке `observability/foundation`.
3. Версия Ильи авторитетна: `check_log_schema.py`, `justfile`, `ci.yml` и `CONTRIBUTING.md` взяты из PR #45.
4. Коммиты — conventional commits с подробным телом: вся контекстная информация в коммите, не в PR-описании.
5. Ничего не включаем в прод до адреса и явного решения: подготовка ≠ включение.
6. Чужие PR и ветки, особенно PR #16, не трогаются.

## Ссылки

- [Runbook](runbook.md) — выкладка, откат, бэкапы, инциденты.
- [Мониторинг](monitoring.md) — логи, метрики, статус алертов.
- [Локальная наблюдаемость](DEV-OBSERVABILITY.md) — контур на высоких портах.
- [Локальный PostgreSQL](DEV-API.md) — гейд CMS API без ручного контейнера.
- [Ротация секретов](SECRET-ROTATION.md) — PAT, Grafana, Postgres, Telegram, Kuma.
- [Шаблон инцидента](incidents/template.md) — влияние, хронология, корень проблемы и action items.
- [Ротация ключа бэкапов](BACKUP-KEY-ROTATION.md) — смена `age`-ключа и перешифрование бэкапов.
- `docs/resource-budget.md` — лимиты и gate включения метрик по ADR 0006 §4.
- [ADR 0005](adr/0005-observability-glitchtip.md) — логи и стек наблюдаемости.
- [ADR 0015](adr/0015-runtime-and-data-operations.md) — неизменяемые артефакты и операции.
- [Issue #9](https://github.com/Sreda-Media/sreda-media/issues/9) — эпик CI и выкладки.
- [Issue #14](https://github.com/Sreda-Media/sreda-media/issues/14) — эксплуатация и мониторинг.

## Идеи на потом

- Полноценная artifact provenance: cosign + attestations после появления реального артефакта.
- Alert-дрилл не только по Loki, но и по Grafana contact point с подтверждением доставки.
- Тонкая настройка порогов алертов по фактическим метрикам, а не на глаз.
- Dependabot/Renovate намеренно не добавляем: создают PR-флуд и мешают принятому trunk-based процессу.
- Kafka не возвращаем: при текущем объёме это лишняя операционная нагрузка.

## Порядок включения SLO-алертов

Включение — отдельный коммит, только после слияния PR #16 и получения адреса Q-1:

1. Заполнить Telegram contact point через env `GRAFANA_TELEGRAM_BOT_TOKEN` и `GRAFANA_TELEGRAM_CHAT_ID`.
2. В `deploy/observability/grafana-provisioning/alerting/rules.yml` заменить `labels.enabled: "false"` на `"true"` только у трёх SLO-правил.
3. В ТОМ ЖЕ коммите включения обновить `scripts/check_alert_rules.py` и
   `scripts/check_slo.py`: разрешить `enabled: "true"` ровно для трёх UID из
   `deploy/observability/slo.json` (`rule_uids`), для остальных правил оставить
   `"false"`. Затем запустить `just check-alerts`, `just check-slo` и `just verify`
   и убедиться, что все проверки зелёные. Пока проверки не обновлены, шаг 3
   завершится FAIL — это ожидаемое поведение текущего контура.
4. Применить `deploy/observability/grafana-dashboards-gated/slo-external.json` после настройки внешнего probe: файл лежит ВНЕ каталога `grafana-dashboards/`, который монтируется в Grafana, поэтому сейчас он не попадает в авто-провизионинг. Job `sreda-external` должен быть настроен в blackbox-экспортере — сейчас его нет ни в одном scrape-конфиге.
5. Записать дату включения в этот раздел.

До выполнения этих шагов алерты остаются выключенными, а `just check-alerts`
проверяет именно выключенное состояние.
