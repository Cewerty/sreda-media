# ADR 0005: Наблюдаемость — GlitchTip без Redis, healthchecks и безопасный контракт логирования

## Дата: 20-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 21-11-2026. Сохранён подход без Prometheus/Grafana/OTel; добавлены контракт событий, очистка данных, ресурсные ограничения и fallback.

## Контекст

Система состоит из статического сайта, Django + django-modern-rest (DMR) CMS, фоновых процессов (варианты исполнения обсуждаются в ADR 0013) и бота. Один Django-монолит может иметь несколько process types; живой HTTP-процесс не доказывает работу scheduler или worker.

Нужно узнавать об ошибках, проваленных сборках и резервных копиях до обращения пользователя. Студенческая команда и VPS-бюджет около 500 ₽/месяц не позволяют бесконтрольно наращивать observability stack. Redis исключён PRD; посетительская аналитика, включая Яндекс Метрику, в MVP не входит и к этому ADR не относится.

Исходное решение использовать GlitchTip сохраняется. По актуальной документации возможен PostgreSQL-only all-in-one режим без Redis/Valkey. Нужен явный ресурсный gate: заявленный минимум одного сервиса не доказывает, что весь проект помещается на выбранном VPS.

## Решение

Использовать **JSON stdout, health/readiness, внешний uptime check, GlitchTip со Sentry SDK и краткие критические алерты в Telegram**. Для GlitchTip выбирать проверенную версию с PostgreSQL-backed queue/cache/session и отключённым Redis/Valkey. Подключение DMR не создаёт отдельной системы логов: используются Django runtime и общие прикладные correlation IDs.

### Детали реализации

#### 1. Контракт событий

Каждое событие содержит `event`, `component`, `operation`, `outcome`, `timestamp`, `environment`, `release`; correlation ID связывает HTTP use case, outbox, попытку и build. Для измеряемой операции добавляется `elapsed_ms`; для доставки — внутренний delivery/attempt ID, канал и безопасная категория ошибки; для build/export/backup — revision/set ID.

Ядро: `process_started/stopped`, `request_finished`, `operation_failed`, `scheduler_tick_finished`, `delivery_finished`, `site_build_requested/finished`, `site_deploy_finished`, `backup_finished`, `export_finished`, `restore_finished`. Имена стабильны; произвольный текст не заменяет машинные поля. Штатные отказы не логируются как необработанные исключения на каждом слое.

Логи пишутся в stdout с ротацией/лимитом на стороне runtime. Actor audit хранится отдельно с ограниченным доступом: JSON stdout не становится базой истории действий редакции.

#### 2. PII policy и Sentry SDK

- По умолчанию не собирать raw request/response bodies, статьи, предложку, Telegram ID/username, provider IDs, имя/фото, cookie, auth headers, DSN с credentials, приглашения, OAuth code/state/verifier и токены.
- Настроить запрет default PII и отправки персонального user context; очищать события, breadcrumbs, URL/query и контекст исключений до отправки в SDK. Access/proxy logs проходят те же правила: callback URL и invite token не попадают в stdout.
- Отчёты содержат разрешённые технические IDs и очищенный stack trace; не включать locals/attachments/replay по умолчанию. Типизированная ошибка DMR наружу — безопасный code и correlation ID, не текст исключения.
- SDK настраивается на bootstrap Django/worker/bot; SDK/alert dependencies внедряются Dishka providers. `traces_sample_rate=0.0`; tracing, session replay и посетительская аналитика не включаются побочно.
- В Telegram отправляется краткая причина, компонент, release и correlation ID; не полный event, stack trace или ссылка с bearer secret.
- Тестовыми синтетическими canary secrets проверяются stdout, reverse proxy logs, breadcrumbs и GlitchTip event. Если очистка не доказана, экспорт этого вида контекста отключается.

#### 3. Health и прогресс

DMR/Django обслуживает `/healthz` без БД и `/readyz` с timeout-проверкой PostgreSQL и фактически используемого media storage. Публичный ответ — только статус и безопасный код, без DSN/пути/исключения. На 0.2 ещё нет обязательной проверки несуществующего media storage.

Worker/scheduler подтверждают progress heartbeat после успешного цикла; monitoring проверяет его свежесть и `failed/unknown` доставки. Telegram/VK/GitHub/GlitchTip не являются синхронными зависимостями readiness CMS. Static uptime проверяет публичный URL и актуальный deployment manifest; последние файлы сайта не требуют CMS.

Критичные события: падение CMS/worker/scheduler, неудачная выкладка, backup/export failure или отсутствие ожидаемого успешного запуска. Алерты дедуплицируются и ограничиваются по частоте. Отказ самого Telegram не запускает рекурсивные уведомления.

#### 4. Ресурсный бюджет и хранение

| Ограничение | Предлагаемый начальный gate |
| --- | --- |
| Деньги | Весь runtime и хранение укладываются в ~500 ₽/месяц; тариф не выбран этим ADR |
| RAM GlitchTip | Планировать до 512 MiB для all-in-one сервиса, проверить фактические пики; PostgreSQL/ОС/другие процессы считаются отдельно |
| Запас RAM хоста | После измерения idle и сценариев публикации/ошибок оставить не менее 20% доступной RAM; отсутствие OOM и рестартов обязательно |
| История событий | Начать с 14 дней, включить штатную очистку и проверить её выполнение |
| Логи и диск | Конечный лимит логов и event storage; alert до 80% заполнения выделенного объёма, без автоматического удаления backup |
| Защита от error storm | Rate limit ingestion/alerts и ограниченный backlog; сбой мониторинга не блокирует приложение |

Это проектные лимиты для проверки, не утверждение об измеренном потреблении. Образ/версию, лимит event storage, настройки retention, quota и результат smoke фиксировать в runbook. Для GlitchTip использовать отдельную БД и пользователя PostgreSQL, не app schema/credentials; дополнительный кластер на первом VPS не обязателен. Отключить Redis/Valkey явно по конфигурации выбранной версии, не слепо копировать sample Compose.

#### 5. Fallback при нехватке ресурсов

Порядок действий: снизить ненужный event volume/retention → проверить all-in-one без Redis → оценить отдельное размещение GlitchTip в том же общем бюджете. Потребление и доступность подтверждаются измерением, не обещанием.

До появления сервисов, к которым применим NFR-OPS-01, достаточно статического uptime и build/deploy alerts. Если GlitchTip не помещается при запуске stateful-компонентов, временный режим — ограниченные JSON logs + uptime/heartbeats + Telegram alerts. Он **не равнозначен** error tracker и не считается автоматическим выполнением NFR-OPS-01.

Для такого режима владелец решения фиксирует исключение/правку ADR и PRD, ответственного и срок возврата к tracker. Нельзя молча отключить GlitchTip, добавить Redis или внешний SaaS с передачей данных без решения. При недоступности уже развёрнутого GlitchTip приложение продолжает работать: logs/alerts остаются, SDK не копит неограниченный буфер.

#### 6. Приёмка и этапы

0.1: внешний uptime и сигналы CI/deploy, без visitor analytics и обязательного GlitchTip для несуществующей CMS. С появлением CMS/worker подключаются JSON logs, probes и error tracking по применимому NFR-OPS-01.

Проверки будущей реализации: синтетическая ошибка DMR/worker появляется с release/correlation ID без canary secrets; один сбой даёт один ограниченный алерт; отказ Telegram не рекурсивен; отказ БД даёт readiness 503 при liveness 200; heartbeat ловит зависший worker; GlitchTip недоступен без влияния на CMS; retention и disk/RAM limits реально работают.

## Альтернативы

- **Prometheus/Grafana/OTel сейчас.** Плюс: дополнительные метрики/трейсы. Минус: не обоснованы масштабом и исключены текущим объёмом PRD.
- **Облачный tracker.** Плюс: меньше локального администрирования. Минусы: отдельное решение о доступности, лимитах, оплате и передаче диагностики.
- **Только logs навсегда.** Плюс: минимальный runtime. Минус: нет группировки/истории ошибок; только согласованный временный fallback.
- **GlitchTip со скрытым Redis/Valkey.** Плюс: готовый sample deploy. Минус: нарушает ограничение PRD и не проходит ресурсный gate.

## Последствия

### Положительные

- [+] Ошибки, progress и доступность проверяются раздельно.
- [+] Диагностика имеет стабильный контракт и не раскрывает контент/идентичности.
- [+] Есть проверяемый вариант GlitchTip без ещё одного брокера и честно описанный fallback.

### Отрицательные

- [-] GlitchTip и его PostgreSQL-данные требуют обновлений, retention и ресурсов.
- [-] Без измерения выбранного VPS невозможно подтвердить бюджет.
- [-] Fallback теряет error grouping; его применение требует явного решения, а не тихой деградации.

Пересмотр при измеренных bottlenecks или изменении числа независимых сервисов. Prometheus/OTel не включаются автоматически при появлении второго процесса.

## Ссылки

- [ADR 0004](0004-micro-cms-django-react.md), [ADR 0006](0006-hosting-draft.md), [ADR 0011](0011-application-architecture-and-boundaries.md), [ADR 0012](0012-reliable-external-effects.md), [ADR 0015](0015-runtime-and-data-operations.md).
- [GlitchTip: install, resource requirements и PostgreSQL-only mode](https://glitchtip.com/documentation/install/).
- [Sentry SDK for Django](https://docs.sentry.io/platforms/python/integrations/django/).
- [PyBot: logging contract](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/009-minimal-logging-event-contract.md).
