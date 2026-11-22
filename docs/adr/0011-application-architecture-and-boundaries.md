# ADR 0011: Layered Architecture и Pragmatic DDD с явными границами Django-приложений

## Дата: 21-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

## Контекст

Проект объединяет статический Astro-сайт, React CMS, Django + DMR и Telegram-бота (исходные ADR 0001, 0004, 0007). Контент-план и редакция работают с одной сущностью `Content` (ADR 0010). Команда небольшая, меняется после 2027 года; код должен оставаться понятным без автора проекта (G-5, NFR-MAINT-01/02).

В PyBot приняты thin handlers, application services, rich ORM models, VO, DI/IoC через Dishka и lookup-контракты. Этот подход переносится в Django + DMR: граф зависимостей собирается контейнером, presentation получает готовые application services, а время жизни зависимостей задаётся явно. DMR поддерживает подключение Dishka через интеграцию `dmr-dishka`. Меняется ORM и transport integration, а не сам принцип DI/IoC. Views, admin actions и фоновые команды не должны независимо собирать сервисы или реализовывать правила редакции и доступа.

Основания: PLAN-02/03/06/07, AUTH-02/04, EDIT-03/07–10. Решение не изменяет продуктовые роли, статусы или выбор DMR.

## Решение

Решено использовать **Layered Architecture + Pragmatic DDD и обязательный DI/IoC через Dishka**: предметные Django apps, тонкие транспортные адаптеры, application services для сценариев и транзакций, rich ORM models для локальных инвариантов, DTO/VO на значимых границах. Django + DMR, бот и фоновые entrypoints используют единый подход к providers и scopes. Абстракции вводятся по необходимости, не для возможной замены Django.

### Детали реализации

#### 1. Модули и направление зависимостей

- `content` владеет `Content`, рубриками, авторскими профилями, сроками и переходами статуса. В 0.4 здесь же находятся версии статей; отдельная сущность «запись плана» не создаётся.
- `accounts` владеет идентичностями, приглашениями и правами сотрудников; читательские возможности добавляются в 0.5, не заранее.
- `publishing` владеет внешними публикациями и состоянием сборок, но не определяет правила редакционного одобрения.
- `notifications` формирует адресные уведомления и напоминания. Durable delivery-контракт общий с `publishing` по ADR 0012.
- Раздел UI «Редакция» не требует отдельного app: выделять его стоит только при самостоятельной ответственности и отсутствии циклов.

Внутри app: `models`, `services`, `schemas`, `selectors`, `api`, `ports` и `adapters` появляются по мере необходимости. Пустая папка на каждый слой не требуется. Между apps используются явные прикладные интерфейсы и необходимые ORM-связи; циклическую orchestration выносить в сервис, не лечить динамическими импортами.

Поток записи: `DMR view / bot handler / management command → application service → model + persistence`. Внешние эффекты выполняются по ADR 0012. Astro и React не получают ORM-объекты и не определяют, какой переход разрешён сервером.

#### 2. Application services и rich models

- Сервис описывает use case (`submit_for_review`, `approve_content`, `publish_content`), проверяет полномочия, загружает данные и владеет `transaction.atomic`.
- Модель отвечает за допустимость перехода и целостность собственного состояния; не запускает workflow, не отправляет Telegram и не читает настройки.
- Просрочка вычисляется по сроку, времени и статусу, не становится новым статусом. Часы передаются явно в проверяемую логику; правила даты/времени — в ADR 0013.
- На 0.2 не вводить payload-иерархию и `ArticleVersion` заранее; следовать этапам исходного ADR 0010.
- Инварианты уникальности, связей и обязательных сочетаний по возможности защищаются ограничениями БД. Защита от конкурентного изменения — блокировка строки или optimistic version check для конкретного use case.
- Не размещать критические бизнес-действия в signals, `save()`-хуках или сериализаторах. Admin, импорт и management commands вызывают те же сервисы для бизнес-переходов. Bulk update, обходящие их, допустимы только в явно проверенной миграции/операторской процедуре.

#### 3. DTO, VO и ошибки

- Входные команды и результаты — строгие типизированные схемы, без свободного `dict`, `Any` и lazy loading на транспортной границе. Использовать выбранный в ADR 0004 механизм схем; Pydantic и msgspec не внедряются одновременно ради одинаковой задачи.
- DTO неизменяемы по контракту; вложенные коллекции также неизменяемы. `frozen=True` само по себе не замораживает вложенный список; копирование с обновлением не считается повторной валидацией.
- VO вводятся при наличии поведения/инварианта: `Deadline`, `Slug`, допустимая embed-ссылка. VO не обязателен для каждого ID или строки.
- Доменные ошибки имеют стабильную семантику (`ContentNotFound`, `InvalidTransition`, `PermissionDenied`), не содержат HTTP-кодов. API переводит их в безопасные error codes и ответы; Telegram использует собственные тексты. Raw исключения БД/SDK наружу не уходят.

#### 4. Persistence и lookup-контракты

Django ORM остаётся persistence-инструментом. Повторяемые выборки оформляются в QuerySet/Manager/selector; repository нужен для сложного самостоятельного контракта доступа, не как обёртка `get/save` для каждой модели. Сервис может обращаться к ORM через эти точки; искусственный Unit of Work поверх Django не требуется.

Прикладные имена: `find_* → T | None`, `get_* → T` или доменная ошибка, `exists_* / has_* → bool`. Поиск коллекции обычно возвращает пустую коллекцию; требование непустого результата должно быть явным. Стандартный `QuerySet.get()` не переименовывается: его исключение преобразуется на persistence/service-границе. Из сервиса наружу не уходит unevaluated QuerySet.

#### 5. Авторизация

- Роль и доступ к конкретному материалу проверяются сервером в каждом use case; фильтрация видимости применяется и к спискам/поиску.
- Трактовку «свои материалы» для соавтора нужно явно закрепить в матрице прав по PRD до реализации; кнопка в React не является проверкой полномочий.
- `admin` не получает неописанную роль редактора автоматически. Фоновые операции имеют явный системный контекст и фиксированный набор разрешённых действий.
- `tach` проверяет запреты: модели не импортируют views/SDK; сервисы не импортируют concrete delivery adapters; app API не зависит от внутренностей другого transport adapter. Поведенческие ограничения проверяются тестами.

#### 6. DI/IoC, providers и composition roots

Переносится контракт PyBot ADR 006 и 013: **зависимый объект объявляет необходимые зависимости, а их создание, выбор реализации и lifecycle принадлежат IoC-контейнеру**. Application service получает persistence-компоненты и порты в конструкторе; адаптер получает SDK-клиент и типизированные настройки. Сервис не создаёт собственные зависимости и не читает глобальный `settings`.

- Providers группируются по ответственности в модуле `di`: конфигурация, persistence, infrastructure adapters, application services. Они связывают порт с реализацией и описывают scopes/finalizers; бизнес-логика в providers не размещается.
- Composition root каждого process type подключает нужные providers и создаёт контейнер один раз при bootstrap. Состав providers общий там, где общие use cases, но экземпляры контейнера и ресурсы не разделяются между процессами.
- DMR controllers получают сервисы через `FromDishka` и sync/async injection из `dmr-dishka`; request lifecycle обеспечивается интеграцией. Совместимые версии DMR, Dishka и integration фиксируются в lockfile. Не подменять эту интеграцию aiogram/FastAPI wiring из PyBot.
- Бот использует интеграцию Dishka с aiogram; management commands, worker и scheduler явно открывают scope операции и получают entrypoint-сервис из него. Один request scope не переиспользуется между updates, заданиями или параллельными обработчиками.
- Обращение к контейнеру разрешено в composition root и transport/runtime integration. Application/domain-код не получает `Container` и не вызывает `container.get()`: это service locator, а не constructor injection.

| Зависимость | Scope | Контракт |
| --- | --- | --- |
| Типизированная runtime-конфигурация | `APP` | Проверяется на bootstrap, внедряется явно |
| SDK/HTTP-клиенты, concrete port adapters | `APP`, если безопасно переиспользование | Создаются providers, закрываются при shutdown; request context внутри не сохраняется |
| Stateless repositories/selectors | `APP` | Не держат текущего пользователя, ORM-экземпляры, QuerySet или транзакцию |
| Application services, actor/request context | `REQUEST` | Отдельные экземпляры на HTTP-запрос, update или фоновую операцию |

Scope выбирается по реальному lifecycle: компонент с request-зависимостью не регистрируется как `APP`. При добавлении состояния или непереиспользуемого клиента provider переводится в подходящий scope, а не скрывает mutable context в singleton. Sync/async container и finalizers соответствуют entrypoint и используемым клиентам.

Django ORM сохраняет штатное управление соединениями; SQLAlchemy `AsyncSession` и `SessionProvider` из PyBot не переносятся. DI scope не заменяет транзакцию: `transaction.atomic` по-прежнему принадлежит application service. Доменные модели и DTO создаются/загружаются по бизнес-сценарию, не регистрируются в контейнере как сервисы.

В тестах providers подменяют внешние порты fake/stub-реализациями без патчей глобальных SDK/settings. При bootstrap проверяется корректность графа зависимостей, а при shutdown закрываются app-scoped ресурсы; завершение request/task scope освобождает его ресурсы и контекст даже при ошибке.

#### 7. Этапы и проверка

В 0.1 применяются читаемость и разделение rendering/validation; статическая сборка не требует Python DI-контейнера. С первого application slice CMS в 0.2 подключаются Dishka, DMR integration и providers. Следующие use cases используют тот же DI-контракт, без ручной сборки графа в каждом controller. Generic repositories для каждой таблицы не вводятся.

Приёмка: unit-тесты VO/переходов, сервисный сценарий без HTTP/внешней сети, PostgreSQL-тест rollback и конкурентного изменения, матрица прав на чтение/запись, безопасный HTTP/Telegram error mapping, `tach check`. API, admin и фоновая команда не должны обходить правила одного сценария.

Для DI приёмка включает сборку provider graph, подмену порта без production SDK, получение сервиса в DMR controller, изоляцию actor context между запросами/задачами и вызов finalizers при успехе, ошибке и shutdown. Это проверки будущей реализации, не требование запускать runtime-тесты при редактировании ADR.

## Альтернативы

- **Полная Clean Architecture с pure entities и repository на каждую модель.** Плюс: независимость от ORM. Минус: дублирование Django-моделей, схем и mapping без реальной потребности в замене ORM.
- **Логика в views/admin/signals.** Плюс: быстрый первый CRUD. Минус: HTTP, бот и scheduler расходятся в правилах, транзакции и эффекты трудно проследить.
- **Ручная сборка сервисов без IoC-контейнера.** Плюс: нет интеграционной зависимости. Минусы: wiring размазывается по controllers/commands, scopes и cleanup поддерживаются вручную; противоречит принятому DI-подходу.
- **Буквальный перенос SQLAlchemy session/providers из PyBot.** Плюс: знакомый persistence wiring. Минус: второй ORM/lifecycle рядом с Django. Отказ от этого варианта не означает отказ от Dishka.

## Последствия

### Положительные

- [+] Общие правила для CMS, бота, импорта и scheduler.
- [+] Транзакции, полномочия и эффекты видны при чтении use case.
- [+] Сохраняется Django ORM без дублирующего слоя сущностей.
- [+] Единые providers и scopes для DMR, бота и фоновых сценариев; зависимости подменяются на уровне контейнера, не через глобальные патчи.

### Отрицательные

- [-] Нужны дисциплина сервисного API и ревью admin/import-путей.
- [-] Rich models связаны с Django; это осознанный компромисс.
- [-] Import-check не доказывает корректность транзакций и доступа.
- [-] Нужны поддержка provider graph, совместимых версий DMR/Dishka integration и дисциплина lifecycle. Этот overhead принят ради явного DI/IoC.

Пересмотр: app приобретает независимый жизненный цикл, возникают устойчивые циклы зависимостей или реальная необходимость заменить persistence. Это основание для нового ADR, не для превентивных микросервисов.

## Ссылки

- Исходные ADR медийки: 0004, 0007, 0009, 0010; PRD 1.4: G-5, PLAN, AUTH, EDIT, NFR-MAINT.
- [ADR 0012: внешние эффекты](0012-reliable-external-effects.md), [ADR 0013: фоновые процессы](0013-background-runtime.md).
- PyBot: [манифест](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/ARCHITECTURE.md), [immutable DTO](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/002-dto-immutability.md), [VO](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/003-introduce-value-objects.md), [rich ORM](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/07-adoption-of-rich-orm-models.md), [lookup](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/008-nullable-and-strict-lookup-separation.md), [presentation](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/015-presentation-layer-module.md).
- Основа DI/IoC: [PyBot ADR 006 — Dishka DI и repositories](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/006-introduction-of-dishka-di-and-repositories.md), [PyBot ADR 013 — явная инъекция и composition roots](https://github.com/Cewerty/PyBot-ITAcadem/blob/51ebfd63f5cd6214dab168ef65c90dabb7a69d17/src/pybot/docs/adr/013-configuration-runtime-boundaries-and-explicit-injection.md).
- [DMR: Bring your own DI](https://django-modern-rest.readthedocs.io/en/latest/pages/integrations.html#bring-your-own-di), [dmr-dishka](https://github.com/arturboyun/dmr-dishka), [Dishka: concepts and scopes](https://dishka.readthedocs.io/en/latest/concepts.html).
- [Django: transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/).
- [Pydantic: faux immutability](https://docs.pydantic.dev/latest/concepts/models/#faux-immutability).
