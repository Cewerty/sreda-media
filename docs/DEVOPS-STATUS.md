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

## Блокирующие зависимости

- **PR #16** — минимальный Astro-сайт в `main`; без него `build-site` честно пропускается.
- **Q-1 с Артёмом** — домен, DNS и тестовый адрес выкладки.
- **ENABLE_DEPLOY / ENABLE_DOCS_PAGES** — флаги включаются отдельно, не «по умолчанию».
- **ADR 0006** — финальное решение о хостинге остаётся за Ильёй.
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
