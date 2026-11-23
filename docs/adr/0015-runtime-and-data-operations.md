# ADR 0015: Явные процессы, конфигурация и проверяемая эксплуатация данных

## Дата: 21-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 23-11-2026. Эксплуатационные этапы согласованы с ADR 0005 и эпиком #14.

## Контекст

Astro-витрина должна работать при отказе CMS/бота (NFR-AVAIL-01/02). С 0.2 появляются PostgreSQL и фоновые операции; с 0.4 БД и media storage становятся источником контента. Ошибка настроек, migration или backup не должна обнаруживаться после потери рабочей версии. После выпуска автора в 2027 году эксплуатация должна быть воспроизводима по документации (G-5).

Из PyBot полезны явная конфигурация, разделение process types, PostgreSQL parity и порядок backup/migration/smoke. Не переносятся отдельный FastAPI health-server, Alembic baseline reset и Redis. Grafana + Alloy + Loki внедряются по ADR 0005, с адаптацией под действующие компоненты и ресурсный бюджет. Хостинг/DNS ещё уточняются в ADR 0006; здесь определяется контракт эксплуатации, не провайдер или тариф.

Основания: NFR-SEC-02–04, NFR-OPS-01–04, NFR-COST-01, NFR-MAINT-01/02; исходные ADR 0005–0009.

## Решение

Решено использовать **явные process types с неизменяемыми артефактами, fail-fast на entrypoint, отдельные migrations/backup и проверяемое восстановление PostgreSQL вместе с медиа**. Dev/test/prod используют один поддерживаемый PostgreSQL major. Проверки конфигурации, доступности и бизнес-прогресса разделяются.

### Детали реализации

#### 1. Процессы и независимость статики

| Process/artifact | Назначение | Когда |
| --- | --- | --- |
| `site` artifact + static server | Последняя успешная сборка, локальные build assets | 0.1 |
| `cms-web` artifact | React frontend, без серверных секретов | 0.2 |
| `cms-api` | Django HTTP, `/healthz`, `/readyz` | 0.2 |
| `scheduler`, `worker` | Планирование и выполнение устойчивых к сбоям задач. Состав процессов и транспорт уточняются в Proposed ADR 0013 | 0.2 |
| `bot` | Входящие updates/диалоги; исходящие уведомления может отправлять worker | По потребности, обязательно для предложки 0.6 |
| `config-check`, `migrate`, `seed` | Явные one-shot операции, не hooks старта web | С 0.2 |
| `backup`, `restore`, `export` | Отдельные команды с ограниченными правами | Backup с 0.2, media/export с 0.4 |

Разные process types могут использовать один image; это не требует микросервисов и отдельных API между каждым процессом. В контейнере нет скрытого multiprocessing для health. `/healthz` Django проверяет Django-процесс, не состояние polling/worker.

Static server отдаёт отдельный release directory. Сборка не изменяет рабочие файлы in-place: сначала проверяется полный артефакт, затем атомарно переключается указатель. Неуспех CMS deploy не удаляет последний site release. Сам VPS/static server остаётся общей точкой отказа, если всё размещено на одном хосте; независимость от CMS не равна независимости от хоста.

#### 2. Конфигурация и preflight

- Env parsing и проверка обязательных параметров выполняются в Django settings/bootstrap и entrypoints. Импорт feature-модуля не создаёт SDK/client, не открывает БД и не требует токенов будущих компонентов.
- Django settings остаются framework-границей конфигурации. На bootstrap проверенные typed config регистрируются в Dishka providers и внедряются сервисам/адаптерам по ADR 0011. Для DMR, бота и фоновых процессов определены composition roots; feature-код не читает глобальные настройки и не собирает зависимости самостоятельно.
- Публичные build-настройки Astro/React отделены от server-only secrets. Read-only CMS token доступен только CI/build, не browser bundle, HTML, source maps и static artifacts.
- Каждый process type проверяет только необходимый ему набор. Статический MVP не требует PostgreSQL, Telegram и VK credentials. Production не допускает debug/небезопасные cookie defaults.
- Изменение настройки сопровождается env example, runtime validation и runbook. Ошибка сообщает имя параметра/правило без значения секрета.
- Перед migration/переключением версии выполняются Django system checks и проектный config-check **из выбранного image** с production settings. Orchestration config проверяется отдельно. Эти проверки не доказывают network readiness или корректность DI.

Схема доменов/origins, CSRF trusted origins, cookie и proxy headers определены в обновлённых [ADR 0006](0006-hosting-draft.md) и [ADR 0009](0009-authentication.md): основной origin `https://sreda.sielom.ru`, React `/cms/`, DMR API `/api/`, host-only session cookie. DNS ещё требует подтверждения. Не считать same-site поддомены автоматически same-origin и не расширять cookie domain/CORS без необходимости. Пароли пользователей не вводятся.

#### 3. PostgreSQL, migrations и выпуск

Поддерживаемый PostgreSQL major фиксируется в runtime/test image tags и runbook; его выбор делается при bootstrap совместно с Django compatibility, не механическим копированием версии PyBot. SQLite не используется как замена интеграционным тестам. В CI schema создаётся Django migrations, не только ORM metadata.

Порядок выпуска CMS:

1. Проверить артефакт, настройки и совместимость текущей схемы с новым и ещё работающим кодом.
2. Получить завершённую резервную копию; остановить rollout, если обязательный backup не удался.
3. Выполнить Django migrations одним выделенным процессом под deploy lock.
4. При необходимости отдельно выполнить идемпотентный seed; не создавать фейковых пользователей в production.
5. Обновить API/worker/scheduler, выполнить smoke и проверку стабильности.

Web/polling restart сам не запускает migration или seed. Предпочитается expand/migrate/contract: удаление старого поля идёт после ухода старых процессов. Необратимые или несовместимые data migrations требуют собственного maintenance runbook, оценки длительности и проверенного восстановления.

Откат image не означает откат schema/data; миграции и seed при image rollback автоматически не повторяются. Если старый image несовместим со схемой, использовать forward fix либо согласованное восстановление, не слепой downgrade. Django migration history нового проекта не сбрасывается по примеру перехода PyBot с SQLite.

#### 4. Liveness, readiness и прогресс

- `/healthz`: быстрый ответ живого HTTP-процесса без вызова БД/внешних API.
- `/readyz`: ограниченная по времени проверка БД и используемого media storage, 200 при готовности, 503 при отказе. Проверка storage использует безопасную операцию в выделенной области; статус не раскрывает пути, DSN и raw exception.
- Telegram/VK/GitHub/GlitchTip/Grafana/Alloy/Loki и uptime monitor не входят в синхронный readiness CMS. Отказ внешней доставки или телеметрии фиксируется самостоятельно и не инициирует restart storm API.
- Worker/scheduler проверяются по process state и heartbeat после успешного цикла, а не ответом Django health. Heartbeat должен различать эпохи запуска, чтобы старый процесс не выдавался за новый.
- Статический сайт проверяется внешним uptime check; наличие HTTP 200 дополняется проверкой release/snapshot revision. Это не доказывает исправность фоновой доставки.

Post-deploy smoke проверяет process types, отсутствие restart-count growth в ограниченном окне, probes, публичный статический URL и heartbeat. На тестовом окружении отказ БД даёт `healthz=200`, `readyz=503`, а последняя статическая статья с локальными картинками остаётся доступна.

#### 5. Backup, export и restore

С 0.2 при появлении stateful CMS выполнять ежедневный PostgreSQL backup с защищённой offsite-копией, обнаружением ошибок и проверкой восстановления БД на тестовых данных до выпуска. С upload media — backup файлов вместе с БД; до выпуска 0.4 проверить согласованное восстановление БД и медиа. Ночной published export по ADR 0014 — переносимый fallback, **не замена** backup черновиков, пользователей, версий и outbox.

Для согласованного backup DB/media использовать maintenance pause записывающих API/admin/worker/scheduler и финализацию immutable media до снимка. Другой online-подход допустим только после проверки согласованности ссылок и полного восстановления. Успешный dump без нужных файлов не считается полным backup. Наименее привилегированный backup process не получает токены соцсетей.

Каждый backup-set имеет manifest: UTC timestamp, image/code revision, schema migration state, content schema version, состав и checksums, отметку завершённости. Неполные наборы не участвуют в restore. Копия на том же VPS/диске не защищает от потери хоста: нужна защищённая копия вне него.

До первого production deploy назначить владельца, период хранения, место внешней копии, дисковый лимит и порядок очистки с учётом NFR-COST-01. Не устанавливать бесконечное хранение и не удалять последнюю проверенную копию. Предлагаемая цель для согласования: RPO до 24 часов при успешных ежедневных копиях; RTO определяется замером restore drill, а не обещанием без измерений.

Restore runbook:

1. Выбрать завершённый set, проверить checksum и совместимость image/schema; сохранить текущее состояние перед заменой.
2. Остановить все записи и delivery workers. Явно подтвердить точную target DB/storage; restore — ручная разрушительная операция, не auto-retry deploy.
3. Восстановить БД и соответствующие media в изолированном окружении, проверить миграции, связи, контрольные материалы и файлы.
4. Перед возвращением в production сверить delivery/build state с внешними площадками: backup мог предшествовать уже успешной отправке. Не запускать восстановленный outbox вслепую.
5. Убедиться в readiness, актуальном snapshot/export и сборке сайта, затем поэтапно вернуть записи и обработчики.

Репетиция: создать контрольные данные → сделать backup → изменить/удалить тестовые данные → восстановить → подтвердить их возврат. Отдельно собрать Astro из published export при недоступной CMS. Зафиксировать время, ошибки и operator steps; формальное наличие архива не является проверкой восстановления.

#### 6. Логи, ошибки и ресурсы

JSON stdout имеет стабильные `event`, `component`, `operation`, `outcome`, correlation ID и при необходимости duration/attempt. Фиксируются lifecycle, delivery, schedule tick, build/deploy, backup/export/restore success/failure. Тексты статей/предложки, Telegram ID, cookie, приглашения и токены не включаются в логи/SDK/алерты. Business audit хранится с ограниченным доступом отдельно.

Uptime Kuma (целевой инструмент внешнего uptime), Grafana + Alloy + Loki (централизованные логи и технические алёрты), GlitchTip (ошибки приложений) и Telegram-уведомления уточнены в [ADR 0005](0005-observability-glitchtip.md): PostgreSQL-only all-in-one режим с явно отключённым Redis/Valkey, безопасный event contract и resource/retention gates. Проверяются очистка событий, доступ и отсутствие рекурсивных алертов. Реальные CPU/RAM/диск всего действующего стека измеряются до deploy; проверяются retention, ограничение объёма, доступ и разделение алёртов. Если выбранная версия требует Redis или бюджет превышен, применяется описанная процедура выбора/fallback с явным решением владельца, не скрытая смена сервиса или обход PRD.

По уточнению владельца проекта Яндекс Метрика и другая посетительская аналитика не входят в MVP 0.1. Их подключение и связанные с ним проверки не являются условием запуска. Этот пункт не относится к техническим логам, healthchecks и диагностике ошибок действующих сервисов.

#### 7. Parity, CI и этапы

Общие image/tool versions, PostgreSQL major, migration path и production-like env contract одинаковы в dev/test/prod; credentials и данные различны. CI не получает production secrets. Unit-тесты работают без сети/БД; интеграционные — на PostgreSQL, migration и locking сценарии не подменяются SQLite.

В 0.1 проверяются только существующие компоненты: сборка, links/schema, performance/a11y/SEO, секреты артефакта, atomic static deploy, внешний uptime и уведомления. В 0.2 добавляются config-check, migrations, rollback compatibility, authorization, runtime smoke, централизованные логи, probes, heartbeat, backup/restore PostgreSQL и error tracking по применимому NFR-OPS-01. В 0.3 — per-channel delivery/recovery и расширение error tracking на автопостинг; в 0.4 — media, export и согласованные restore drills БД/медиа.

Path-aware CI всегда выдаёт итоговый обязательный status, включая docs-only PR; shared package, lockfile и contract changes проверяют всех потребителей. Runbook содержит точные команды выбранной инфраструктуры, владельцев, точки диагностики и последние результаты drills. Этот ADR не заменяет будущий исполнимый runbook.

## Альтернативы

- **Migration при старте web.** Плюс: меньше deploy steps. Минус: каждый restart меняет schema и создаёт гонки нескольких процессов.
- **Отдельный health-server как в PyBot.** Плюс: повторное использование кода. Минус: лишний процесс, его здоровье не доказывает здоровье Django/worker.
- **SQLite локально и в тестах.** Плюс: проще запуск. Минусы: другой dialect, транзакции, блокировки и constraints не проверяют production-поведение.
- **Только dump на том же volume.** Плюс: дёшево. Минусы: потеря хоста/медиа и непроверенный restore остаются незакрытыми.

## Последствия

### Положительные

- [+] Ошибки конфигурации ловятся до изменения схемы/трафика.
- [+] Последняя статика сохраняется при отказе CMS; восстановление данных воспроизводимо.
- [+] Релиз проверяет HTTP, фоновые процессы и данные отдельно, без ложной готовности.

### Отрицательные

- [-] Несколько process types и maintenance-процедур требуют владельца эксплуатации.
- [-] Внешний backup, observability stack и media могут не поместиться в исходный бюджет без уточнения состава.
- [-] Для согласованного backup/несовместимой migration возможна короткая пауза записей; статика при этом работает.

Пересмотр: новый хостинг/managed DB, несколько серверов, жёсткие RPO/RTO или невозможность выдержать ресурсный бюджет. Не добавлять observability stack или брокер без изменения соответствующих решений.

## Ссылки

- Исходные ADR медийки: 0005–0009; PRD: NFR-AVAIL, NFR-SEC, NFR-OPS, NFR-COST, NFR-MAINT.
- [ADR 0011](0011-application-architecture-and-boundaries.md), [ADR 0012](0012-reliable-external-effects.md), [ADR 0013](0013-background-runtime.md), [ADR 0014](0014-cross-stack-content-contract.md).
- PyBot: [границы конфигурации](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/013-configuration-runtime-boundaries-and-explicit-injection.md), [process types](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/014-health-api-as-dedicated-process-type.md), [PostgreSQL parity](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/017-postgresql-only-runtime-and-baseline-reset.md), [deployment](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/DEPLOYMENT.md).
- [Django: deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [migrations](https://docs.djangoproject.com/en/5.2/topics/migrations/).
- [PostgreSQL: backup and restore](https://www.postgresql.org/docs/current/backup.html).
