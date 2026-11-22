# ADR 0009: Аутентификация — читатели через VK ID и Telegram Login, сотрудники через Telegram Login по приглашению

## Дата: 20-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 21-11-2026. Уточнены DMR session/CSRF, Dishka, одноразовые приглашения и серверные полномочия.

## Контекст

В системе два вида пользователей.

**Читатели сайта.** Глава медийки уточнила (20-11-2026), что в минимуме к запуску под «профилем» имелся в виду профиль читателя: имя и аватарка, закладки, избранные рубрики. Комментарии появятся позже, «в последний момент». Приоритет на старте — чтобы сайт работал и показывал видео. Аудитория внешняя: программисты, студенты, выпускники, работающие разработчики. Продвижение идёт через паблики VK, Rutube, YouTube, TikTok и Instagram, Telegram-канал медийки.

**Сотрудники CMS** (ADR 0004): авторы и редакторы, сейчас около трёх человек, через полгода 5–6. Все в Telegram. Уведомления CMS уходят в Telegram (ADR 0004), поэтому системе нужно знать Telegram-ID каждого сотрудника.

Ранее предполагалась авторизация через систему колледжа: руководство клуба готово её предоставить, но протокол неизвестен. Глава медийки авторизацию через колледж не предлагала. Проект задуман как внешний, за пределами колледжа.

Ограничения:

- сайт статический (ADR 0001), аутентификация делается отдельным API и островом на сайте;
- у команды мало времени на сопровождение. Пароли, сброс пароля, подтверждение почты и защита от перебора — лишняя работа и лишняя поверхность атаки;
- загружаемые пользователями картинки нужно модерировать, а модерировать некому;
- хранение данных пользователей подпадает под закон о персональных данных (152-ФЗ).

## Решение

Принято решение **не использовать авторизацию колледжа и не делать свои пароли**:

- **читатели** входят через **VK ID** и **Telegram Login**;
- **сотрудники CMS** входят через **Telegram Login**, и только по приглашению.

Причины:

- аудитория уже живёт в VK и Telegram, вход в один клик;
- имя и аватарка, которые нужны в профиле, приходят от провайдера готовыми;
- не нужно хранить пароли, делать сброс пароля и подтверждение почты;
- для сотрудников связка «аккаунт CMS — Telegram-ID для уведомлений» получается автоматически;
- нет зависимости от системы колледжа и от сроков, в которые её предоставят.

### Детали реализации

#### 1. DMR, Django sessions и DI

Приложение `accounts` в `cms-api` обслуживает auth через **django-modern-rest controllers** под `/api/auth/`. Контроллер получает authentication/invitation/application services через **Dishka + dmr-dishka**, проверяет transport-схему и возвращает безопасный typed response. SDK-клиенты, часы и persistence внедряются providers; service locator и auth logic в middleware/signals не используются.

Browser/API используют **Django database-backed sessions**, не собственный JWT в localStorage и не Redis. DMR `DjangoSessionSyncAuth` или `DjangoSessionAsyncAuth` выбирается по endpoint; все session-auth изменения защищены CSRF. На login/bootstrap endpoints до наличия пользователя CSRF включается явно: нельзя рассчитывать, что один установленный Django middleware снимает CSRF exemption любого DMR controller.

Локальный Django user связывается с `ProviderIdentity(provider, provider_user_id)`, на пару действует unique constraint. Username/имя/аватар — не идентичность и не ключ поиска аккаунта. Пользователи создаются с unusable password; своего password flow и обходного парольного admin login нет.

#### 2. Invite token и выдача прав

- Приглашение создаёт уполномоченный editor/admin через use case с проверкой права выдать конкретную роль. Роль задаётся сервером, не принимается из callback/form как доверенная; приглашение не позволяет выдать больше полномочий, чем разрешено issuer.
- Ссылка содержит криптографически случайный opaque token с минимум 256 бит энтропии. В БД хранятся **digest/hash**, role, issuer, expiry, revoked/consumed state и время использования; raw token возвращается только при выдаче и не восстанавливается из БД.
- Токен не логируется, не уходит в SDK/analytics/referrer. Предпочтительно передать его через URL fragment в React invite page, затем POST body в auth begin с CSRF и удалить fragment из адресной строки. Серверная страница не загружает сторонние ресурсы с invite URL.
- Begin создаёт короткоживущий server-side auth flow, связанный с браузерной сессией и invite. Открытие ссылки и предпросмотр мессенджером **не расходуют приглашение**.
- После успешной проверки Telegram identity приложение в одной `transaction.atomic` блокирует invite/проверяет digest, срок, revoked/consumed, допустимую роль и уникальность identity. Создание/привязка сотрудника, назначение разрешённой роли, `consumed_at` и audit commit происходят атомарно.
- Два завершения одного invite не могут создать двух сотрудников. Ошибка/конфликт откатывает и создание, и consume. Expiry/revoke повторно проверяются в финальной транзакции, не только на begin.
- Сотрудник с существующим активным аккаунтом входит без нового invite; неизвестный Telegram ID без действительного invite не получает CMS-доступ. Reader login не создаёт staff role.

#### 3. Telegram Login и VK ID

Для Telegram сохраняется выбранный исходным ADR **Login Widget protocol**. Адаптер проверяет HMAC-SHA-256 согласно официальной схеме с ключом от bot token, constant-time comparison, свежесть `auth_date` и недопустимые будущие timestamps. Ограниченный TTL/clock skew задаётся конфигурацией.

Верификация подписи не заменяет browser-flow binding: callback/POST должен соответствовать начатому login flow, nonce/CSRF и текущей сессии; flow одноразовый и короткоживущий. Не доверять только `id` из JS или повторно использованному signed payload. Для публичного виджета удобно принять данные через JS callback и same-origin POST с CSRF, а не складывать их в access-log query string.

Для VK ID — authorization code flow с **PKCE S256**. `state` — случайный, ограниченный по сроку и одноразовый, привязан к server-side session/flow, provider и разрешённому redirect URI. `code_verifier` хранится на сервере; callback обязан проверить flow/state до завершения login. Provider error, истёкший/повторный state или неверный verifier не создают сессию. Client secret, code и provider tokens не выдаются React.

Сетевой обмен с provider выполняется **вне долгой бизнес-транзакции**; финализация flow и локальные изменения выполняются атомарно, с защитой от повторного consume. Отказ провайдера не создаёт частично привязанного staff account. Provider adapters возвращают проверенную identity DTO, не raw SDK response.

State/PKCE относятся к OAuth flow VK; их нельзя механически заменить HMAC-проверкой Telegram или наоборот. При переходе Telegram на другой официальный login/OIDC protocol нужен отдельный адаптер и обновлённый контракт проверки, не смешение протоколов.

#### 4. Сессии, rotation и отзыв доступа

Публичный origin и пути фиксированы [ADR 0006](0006-hosting-draft.md): `https://sreda.sielom.ru`, `/cms/`, `/api/`. Session cookie — `HttpOnly`, `Secure`, `SameSite=Lax`, host-only, без broad Domain; CSRF token передаётся штатно, независимо от session cookie.

Использовать Django login/session lifecycle: при успешном login ключ сессии обновляется, при logout сессия очищается. При смене privilege/deactivation активные sessions отзываются либо проверяются по authz version/current role на **каждом защищённом use case**. Данные роли в старой cookie не являются источником полномочий.

Django admin также использует проверенную identity и явный admin access, а не скрытый password bypass. Return URL только из внутреннего allowlist, без open redirect. Origin/CSRF/proxy settings минимальны; production debug запрещён. Истёкшие flows/invites/sessions очищаются по конечной retention.

#### 5. Object-level authorization

DMR auth устанавливает активного actor; application service проверяет действие и конкретный объект по ролям PRD:

- author — свои материалы; observer — только разрешённое чтение плана/дашборда;
- trusted_author — дополнительно правка своих опубликованных статей по EDIT-10;
- editor — редакционные действия над всеми материалами;
- admin — управление пользователями/ролями, не неявное право редактировать любые статьи.

Трактовка «свои» для соавторов закрепляется явной матрицей до реализации. Видимость фильтруется в list/detail/search; защита не сводится к скрытию кнопки. Callback identity, invitation role и actor ID нельзя подменить client payload. Фоновые/system actors выполняют только объявленные действия, не обходят policy через общий superuser.

#### 6. Audit и минимальные данные

В закрытом business audit фиксируются issuer, invite lifecycle без raw token, successful/failed login categories, role changes, deactivation/session revoke и запреты критичных действий. В stdout/GlitchTip идут только разрешённые correlation IDs и безопасные категории по [ADR 0005](0005-observability-glitchtip.md), без provider IDs/tokens/state/verifier/cookie. Audit не становится бесконечным архивом private payload.

Reader profile: provider ID, display name, URL аватарки, дата регистрации, bookmarks/рубрики; почта/телефон не запрашиваются. Имя/аватар обновляются при login, загрузки пользовательских картинок нет. При первом reader login local bookmarks сливаются идемпотентно. Привязка второго provider — отдельный поздний use case; автоматически объединять по имени/аватару нельзя.

Политика, согласие и физическое удаление reader account остаются требованиями 0.5 и открытым вопросом PRD о персональных данных. Этот ADR не добавляет visitor analytics: Метрика на старте не требуется.

#### 7. Этапы и проверки

0.1: аккаунтов нет. 0.2: Telegram staff login, hashed/atomic invite, DMR sessions/CSRF, audit и object policy. 0.5: reader Telegram/VK, bookmarks и удаление.

Проверки будущей реализации: два одновременных consume одного invite; expiry/revoke между begin/finish; role tampering; identity conflict с rollback; replay HMAC/state; login CSRF/session fixation; неверный PKCE; недоступный provider; отзыв старой session после deactivation; список чужих материалов; admin/worker не обходят policy; canary secret отсутствует в proxy/stdout/SDK. Provider callback contract проверяется против выбранных версий SDK/protocol.

## Альтернативы

* **Авторизация через систему колледжа:**
  * *Плюсы:* руководство клуба готово её дать, все студенты уже в системе.
  * *Минусы:* аудитория сайта внешняя, у читателей нет аккаунтов колледжа. Выпускники и гостевые авторы туда тоже не попадут. Протокол неизвестен, а сроки зависят от колледжа. Глава медийки этот вариант не предлагала.

* **Свои логин и пароль (почта + пароль):**
  * *Плюсы:* нет зависимости от сторонних провайдеров, полный контроль.
  * *Минусы:* хранение паролей, сброс, подтверждение почты, защита от перебора, почтовый сервис — много работы и поверхность атаки. Читателю нужно заводить ещё один пароль, а аватарку пришлось бы загружать и модерировать.

* **Яндекс ID / Google:**
  * *Плюсы:* массовые провайдеры.
  * *Минусы:* аудитория медийки сосредоточена в VK и Telegram. Google в РФ работает нестабильно. Яндекс ID можно добавить позже как третий провайдер, если появится запрос.

* **Загрузка аватарок на сайт:**
  * *Плюсы:* читатель выбирает любую картинку.
  * *Минусы:* нужна модерация пользовательского контента, хранилище и обработка изображений. Модерировать некому.

## Последствия

### Положительные

* [+] Нет паролей: нечего утекать, сбрасывать и подтверждать.
* [+] Вход в один клик для аудитории из пабликов, имя и аватарка без загрузки.
* [+] Уведомления CMS автоматически знают Telegram-ID сотрудника.
* [+] Нет зависимости от колледжа, вопрос с его протоколом авторизации снимается.
* [+] Нет пользовательских картинок, которые нужно модерировать.

### Отрицательные

* [-] Зависимость от VK и Telegram: если провайдер недоступен или поменяет API, вход ломается.
* [-] Читатели без VK и Telegram войти не смогут.
* [-] Появляются персональные данные: политика, согласие, удаление аккаунта и, возможно, формальности по 152-ФЗ.
* [-] Без загрузки аватарок их нельзя поменять на сайте, только у провайдера.
* [-] Привязка к одному сайту для cookie зависит от того, как выдадут DNS (ADR 0006).

## Ссылки

* [Telegram Login Widget](https://core.telegram.org/widgets/login)
* [VK ID для бизнеса](https://id.vk.com/about/business)
* [152-ФЗ «О персональных данных»](https://www.consultant.ru/document/cons_doc_LAW_61801/)
* ADR 0001, ADR 0004, ADR 0006, ADR 0008


* [ADR 0011 — DI/IoC](0011-application-architecture-and-boundaries.md), [ADR 0012 — внешние эффекты](0012-reliable-external-effects.md).
* [DMR: Django session auth](https://django-modern-rest.readthedocs.io/en/latest/pages/auth/django-session.html), [CSRF и integrations](https://django-modern-rest.readthedocs.io/en/latest/pages/integrations.html#csrf).
* [Django: login/session lifecycle](https://docs.djangoproject.com/en/5.2/topics/auth/default/#how-to-log-a-user-in), [OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700.html).
