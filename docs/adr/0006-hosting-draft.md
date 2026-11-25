# ADR 0006: Публичный VPS, Caddy и same-origin схема сайта/CMS

## Дата: 20-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 23-11-2026. Добавлены поэтапный observability stack и ресурсная проверка по ADR 0005, эпик #14. Схема размещения выбрана; провайдер/тариф, подтверждение DNS и владелец эксплуатации после 2027 года остаются неподтверждёнными.

## Контекст

PRD уже определяет домен `sreda.sielom.ru`, оплату Ильёй и бюджет около 500 ₽/месяц. Сервер клуба есть, но без публичного IP; готовой публичной production-площадкой он не является. Прежние вопросы «кто платит» и «какой домен» закрыты этими фактами.

Нужно разместить Astro-сайт, React CMS, Django-modern-rest (DMR), PostgreSQL, фоновые процессы и error tracker. Превью статей рендерит CMS: wildcard DNS/TLS и PR previews для этого не нужны. Витрина должна отдавать последнюю сборку при отказе CMS.

## Решение

Выбран **один публичный VPS с Caddy и Docker Compose**, основной origin **`https://sreda.sielom.ru`**, React под `/cms/` и **DMR API под `/api/`**. Это выбор topology, не покупка неизвестного тарифа. Сервер клуба может стать вспомогательным/offsite узлом после проверки доступа и независимости хранения, но публичный production не зависит от недокументированного туннеля.

### Детали реализации

#### 1. Маршрутизация и TLS

| Путь | Назначение |
| --- | --- |
| `/` | Astro release, статьи, RSS и локальные assets |
| `/cms/` | React artifact с router basename/asset base `/cms/` |
| `/api/` | DMR API; reverse proxy сохраняет префикс, совпадающий с Django routing |
| `/api/auth/` | Telegram/VK callbacks, session endpoints |
| `/admin/` | Django admin для уполномоченных разработчиков |
| `/static/` | Отдельная collected-static директория Django admin |
| `/healthz`, `/readyz` | Django probes, не состояние worker/бота |

Caddy направляет API/admin/probes прежде статического fallback. SPA fallback действует только внутри `/cms/`: API 404 не превращается в React index с 200. Private draft media не выставляются публичной директорией; build API выдаёт только разрешённые published assets.

`cms.sreda.sielom.ru` не обязателен; при подтверждении дополнительного DNS допустим canonical redirect на `/cms/`, а не ещё один auth origin. GlitchTip остаётся внутренним сервисом; публичный DSN/UI требует подтверждённого отдельного hostname с TLS либо проверенной поддержки proxy base path. Эти детали не выдаются за уже согласованные DNS-записи.

Согласовать A/AAAA и ACME challenge с Артёмом по Q-1 PRD. Caddy хранит ACME data persistently и продлевает сертификат; wildcard/on-demand TLS не prerequisite MVP. Host и proxy headers проверяются Django; доверять только известному reverse proxy.

#### 2. Same-origin session API

React обращается к `/api/` на том же origin. Session cookie — host-only, `HttpOnly`, `Secure`, `SameSite=Lax`, без широкого `Domain`; path покрывает API/admin и reader endpoints. Broad CORS/credentialed cross-origin requests по умолчанию отсутствуют. CSRF передаётся штатным механизмом Django.

DMR session auth и CSRF описаны в [ADR 0009](0009-authentication.md). Same-site поддомены не равны same-origin. Redirect URI провайдеров регистрируются точно; return URL ограничены внутренними разрешёнными путями. Отдельного парольного backdoor для admin не создаётся.

#### 3. Process topology и данные

- С 0.2 (состав фоновых процессов уточняется в ADR 0013): `cms-api`, `scheduler`, `worker`, `postgres`, Caddy/static server.
- `bot` polling нужен для входящих updates/диалогов; исходящие напоминания может отправлять worker.
- `config-check`, `migrate`, `seed`, `backup`, `restore`, `export` — явные one-shot operations по [ADR 0015](0015-runtime-and-data-operations.md).
- Каждый Python-процесс имеет собственный Dishka container; HTTP/update/job — отдельный scope по ADR 0011.
- PostgreSQL и private storage не публикуются открытыми host ports. App data, media, ACME data и backup размещаются в отдельных persistent областях с ограниченными правами.
- 0.1: Caddy и внешний uptime monitor (целевой Uptime Kuma); независимая точка проверки предпочтительна, ограничение при размещении на основном VPS фиксируется в runbook.
- 0.2: по ADR 0005 подключаются Grafana, Alloy, Loki и PostgreSQL backup с защищённой offsite-копией. Grafana доступна уполномоченным операторам через согласованный защищённый маршрут; Alloy/Loki и PostgreSQL не выставляются публичными host ports. Отдельные DNS-записи и размещение уточняются по потребности.
- GlitchTip запускается по ADR 0005 без Redis/Valkey, с отдельной БД и пользователем; подключается по применимому NFR-OPS-01, на 0.3 расширяется на автопостинг. Ни один observability-сервис не входит в readiness CMS.

Static deploy проверяет полный release и переключает его атомарно. Отказ/рестарт CMS не очищает последнюю статику. Один VPS остаётся общей точкой отказа: при потере хоста требуется offsite backup и восстановление, а не только restart приложения.

#### 4. Ресурсный gate и конкретный VPS

Предлагаемая стартовая цель — 1 vCPU, 2 GiB RAM, SSD с местом под DB/media, минимум два static release и ограниченную retention backup/logs. Это исходная оценка для замера, а не подтверждённая конфигурация для всего стека Grafana/Alloy/Loki/GlitchTip и не обещание тарифа за 500 ₽.

Перед выбором записать провайдера, тариф, дату цены, весь ежемесячный платёж с IPv4/backup, RAM/CPU/disk, доступность SSH и переносимость данных. Проверить совместные idle/peak API/worker/PostgreSQL/Caddy/GlitchTip/Grafana/Alloy/Loki и Uptime Kuma при фактическом размещении, CPU/RAM/диск, retention, offsite backup, запас ресурсов и restore time. Измерения и сравнение размещений выполняются до соответствующего релиза по ADR 0005. Покупка не выполняется этим ADR. Если бюджет не сходится, требуется решение по бюджету/размещению, не скрытое удаление backup или monitoring.

#### 5. Владельцы и незакрытые пункты

| Пункт | Известно | Требуется подтвердить |
| --- | --- | --- |
| Владелец решения/оплата | Илья по PRD | Конкретный тариф после выбора |
| DNS | Домен выделен; контакт Артём | Реальные записи, ACME path, дополнительные имена при необходимости |
| Infra epic | В roadmap указан Костян | Это не автоматически production on-call |
| Текущая эксплуатация | Нужен явно назначенный ответственный | Имя/контакт, доступ и backup/patch/TLS обязанности до CMS production |
| После 2027 года | Требование передачи G-5 | Преемник, резервный контакт, дата передачи и самостоятельный restore drill |
| VPS | Публичная VPS topology | Провайдер/тариф/IP не предоставлены и не выдуманы |

Runbook содержит deploy/rollback/restore и границы доступа. Перед передачей новый участник разворачивает систему и восстанавливает контрольные данные без автора. Назначать человека on-call только на основании его имени в roadmap нельзя.

#### 6. Этапы и проверки

0.1: DNS/HTTPS, static artifact и сохранение прошлого release при failed deploy; аналитика не нужна. 0.2: `/cms/`/`/api/` routing, DMR session/CSRF, закрытые DB ports и процессные smoke. 0.4: build assets автономны от CMS, восстановление DB/media/export проверено.

Проверить API 404 без SPA fallback, login без broad cookie domain, отказ CMS без потери статей/картинок, TLS renew и backup alerts с владельцами. Эти проверки относятся к будущему deploy, не отчёт о выполненной эксплуатации.

## Альтернативы

- **Сервер клуба без публичного IP.** Плюс: готовое оборудование. Минусы: доступность/туннель/оператор не решены.
- **Разные site/CMS origins.** Плюс: раздельное размещение. Минус: лишние DNS/cookie/CORS/CSRF зависимости.
- **Nginx.** Плюс: зрелая знакомая платформа. Минус: другая процедура TLS/config; Caddy выбран ради небольшого operational surface.
- **Static hosting + VPS.** Плюс: сайт переживает отказ VPS. Минус: второй deploy/control plane; возможное будущее решение.
- **Managed platform.** Плюс: меньше администрирования. Минусы: бюджет, доступность и переносимость требуют сравнения.

## Последствия

### Положительные

- [+] Один origin и session-based DMR API без лишнего CORS.
- [+] CMS не является runtime-зависимостью последней статики.
- [+] Зафиксированы process topology и незакрытые операционные вопросы.

### Отрицательные

- [-] Один VPS — точка отказа, данные и доступы требуют сопровождения.
- [-] Тариф и оператор после 2027 года пока не подтверждены.
- [-] Ресурсы/бюджет необходимо измерить на фактической площадке.

## Ссылки

- [ADR 0004](0004-micro-cms-django-react.md), [ADR 0005](0005-observability-glitchtip.md), [ADR 0008](0008-db-source-of-truth.md), [ADR 0009](0009-authentication.md).
- [ADR 0011](0011-application-architecture-and-boundaries.md), [ADR 0013](0013-background-runtime.md), [ADR 0015](0015-runtime-and-data-operations.md).
- [Caddy: handle](https://caddyserver.com/docs/caddyfile/directives/handle), [automatic HTTPS](https://caddyserver.com/docs/automatic-https).
