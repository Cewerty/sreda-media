# ADR 0010: Модель материала — `Content` с типом `ContentKind` и payload в виде tagged union

## Дата: 21-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 21-11-2026. Уточнены DMR/Dishka, JSON validation, ограничения БД и versioned payload.

## Контекст

Изначально главной сущностью CMS была статья (`Article`, ADR 0004). После уточнения у руководства клуба (Панасеня, 20-11-2026) появилось требование к **панели контент-плана**. Руководству и главе медийки нужно видеть, что запланировано, кто отвечает, к какому сроку, и что просрочено («обещали подкаст и ролик про перфокарты, а его нет»). Позже материалы должны публиковаться не только на сайт, но и в соцсети.

Медийка выпускает разные материалы: статьи, видео, подкасты, посты. У них есть:

- **общее** — планирование и жизненный цикл: ответственный, плановая дата, статус, рубрика;
- **специфичное** — данные и правила по типу:
  - у статьи есть текст в Markdown с версиями и историей правок, редакционное одобрение разрешает включить её версию в published snapshot; фактическая выкладка сайта учитывается отдельно (ADR 0008);
  - видео живёт на внешней площадке (VK, Rutube, YouTube). «Опубликовано» означает, что ролик выложен и ссылка на него добавлена в материал;
  - у подкаста аудио или видео эпизода и, возможно, расшифровка.

Нужно решить, как моделировать это в домене и хранить в Django так, чтобы:

- не скатиться в Primitive Obsession (тип строкой, URL строкой, срок голым `datetime`);
- инкапсулировать правила, специфичные для типа, а не размазывать `if kind == "video"` по сервисам;
- добавлять новые типы без переделки общей части;
- соответствовать архитектурному манифесту: Pragmatic DDD, rich models, композиция вместо наследования, абстракция только там, где она окупается.

## Решение

Принято решение моделировать материал как **одну сущность `Content`** (корень агрегата), у которой есть:

- **общие поля планирования** — в самой сущности, с мелкими Value Objects вместо примитивов;
- **тип** — `ContentKind` (enum);
- **данные по типу** — `payload` в виде **tagged union** из типизированных объектов, а не через наследование.

### Детали реализации

1. **Тип материала — enum, а не строка:**

   ```python
   class ContentKind(StrEnum):
       ARTICLE = "article"
       VIDEO = "video"
       PODCAST = "podcast"
       POST = "post"
   ```

2. **Общая часть (планирование) — в `Content`**, с мелкими VO:
   - `Deadline` — плановая дата, метод `is_overdue(now)`;
   - `Slug` — проверка формата при создании;
   - ответственный (ссылка на пользователя), статус (`ContentStatus`), рубрика.

3. **Данные по типу — payload.** Не каждый payload — это Value Object:
   - **`VideoEmbed`, `PodcastPayload`, `PostPayload` — Value Objects.** Идентичности нет, неизменяемые, проверяются при создании, заменяются целиком. `VideoEmbed` проверяет URL, определяет площадку (VK, Rutube, YouTube) и строит ссылку для эмбеда;
   - **статья — не VO.** У текста есть версии и история, то есть идентичность и жизненный цикл. `ArticleVersion` — сущность внутри агрегата `Content`, а `ArticlePayload` хранит ссылку на одобренную версию.

4. **Правила по типу инкапсулированы в payload.** `Content.publish()` спрашивает payload, что мешает публикации, и не знает деталей конкретного типа:

   ```python
   @dataclass(frozen=True, slots=True)
   class VideoEmbed:
       url: str

       def __post_init__(self) -> None:
           if detect_provider(self.url) is None:
               raise InvalidEmbedUrl(self.url)

       def publish_blockers(self) -> list[str]:
           return []  # ссылка есть и валидна, значит, видео уже выложено


   @dataclass(frozen=True, slots=True)
   class ArticlePayload:
       approved_version_id: int | None

       def publish_blockers(self) -> list[str]:
           return [] if self.approved_version_id else ["Нет одобренной версии"]


   Payload = ArticlePayload | VideoEmbed | PodcastPayload | PostPayload


   class Content(models.Model):  # rich model
       def publish(self) -> None:
           if blockers := self.payload.publish_blockers():
               raise CannotPublish(blockers)
           self.status = ContentStatus.PUBLISHED
   ```

5. **Ветвление по типу в сервисах** — только через `match` с исчерпывающей проверкой, чтобы mypy или pyright указали на необработанный тип при добавлении нового:

   ```python
   match content.payload:
       case ArticlePayload():
           record_site_build_intent(content)  # outbox в транзакции, не вызов SDK
       case VideoEmbed() | PodcastPayload() | PostPayload():
           record_publication_change(content)  # не запускает кросспостинг вне сайта
       case _:
           assert_never(content.payload)
   ```

6. **Хранение в Django:**
   - `kind` — поле с choices из `ContentKind`;
   - `payload` — `JSONField`, который сериализуется в VO и обратно через msgspec или pydantic на границе модели (свойство или кастомное поле). В сервисы и домен уходит только типизированный объект, не `dict`;
   - согласованность `kind` и discriminator payload проверяется явно до persistence и дополнительно PostgreSQL constraints по правилам ниже; одного `save()` или `choices` недостаточно;
   - `ArticleVersion` — отдельная таблица со ссылкой на `Content`.

7. **Этапы внедрения**, чтобы не строить абстракцию заранее:
   - **0.2 (панель контент-плана):** `Content` с `kind`, общими полями планирования, `Deadline` и необязательной внешней ссылкой. Поведения по типам почти нет, полноценные payload не вводятся;
   - **0.4 (редактор статей):** вводятся payload-VO и `publish_blockers()`, `ArticleVersion`, ветвление через `match`. Это рефакторинг по реальной потребности: на этом этапе логика типов действительно расходится.

#### Контракт JSON ↔ typed payload

В 0.4 persisted payload имеет явный envelope `{kind, schema_version, data}`; discriminator должен совпадать с внешним `Content.kind`. Для каждого kind/версии определена строгая схема в выбранном механизме msgspec/Pydantic. Неизвестные поля/типы/версии не превращаются в `{}`, default article или permissive dict.

- DMR request/response schemas типизированы; controller получает application service через Dishka, а не выполняет JSON/ORM mutation сам.
- Application service валидирует DTO, проверяет actor и ревизию, вызывает rich model, затем persistence сериализует validated payload. На чтении JSON декодируется в тот же typed union; повреждённое/неизвестное состояние даёт явную ошибку и безопасную диагностику.
- `full_clean()`/validators не считаются автоматически вызываемыми каждым `save()`; `choices` тоже не обеспечивают всё ограничение БД. Вызов validation и ограничения должны быть явными.
- Root JSON должен быть object с ожидаемыми discriminator/version/data. PostgreSQL CHECK constraints защищают допустимый `kind`, совпадение JSON tag и колонки, наличие/JSON-типы обязательных envelope полей и поддерживаемые на данном этапе schema versions. Пропущенное/null поле не должно пройти из-за SQL UNKNOWN: выражение ограничения явно отклоняет этот случай.
- URL allowlist, сложные правила публикации, принадлежность article version конкретному Content и её approved state проверяются в модели/сервисе. JSON reference не является foreign key; deletion/version changes проходят контролируемый use case. Где нужна строгая ссылочная целостность, связь хранится нормализованным FK, а не полагается на число внутри JSON.
- Typed payload не делает неверную сущность автоматически допустимой: статья требует согласованной версии/статуса/полномочий, видео — проверенной ссылки по своим правилам. `publish_blockers()` в примере выше — часть проверки, не замена всей state machine.

#### Защита путей записи

Операции создания/редактирования/публикации выполняются application services в `transaction.atomic`, с lock/version check там, где возможна гонка. Django admin, импорт, бот и management commands используют этот же API; signals и DMR serializer не становятся альтернативными бизнес-сервисами.

Запрещены обычные `QuerySet.update()`, `bulk_update()`, `bulk_create()` и raw SQL, меняющие kind/payload/status/approval в обход validated use case. Нельзя обойти правило, заявив «валидация уже есть в frontend». Ограничение не запрещает эффективные batch-операции вообще: они допустимы только в явно спроектированном batch use case с теми же инвариантами либо проверенной data migration.

Миграция payload включает schema/data/constraints в одном change set, прогон на реальной PostgreSQL и сверку существующих записей. Post-save signal не является страховкой от bulk update: такие пути должны предотвращаться организацией persistence API и DB constraints.

#### Версионирование и rollout

`payload.schema_version` — версия хранения конкретного payload. Она отлична от public content schema и HTTP API version по [ADR 0014](0014-cross-stack-content-contract.md).

Breaking change выполняется по expand/migrate/contract: reader поддерживает старую и новую форму → data migration явно преобразует/валидирует записи → новый writer → проверка всех данных → сужение DB constraints/удаление старого reader. Для каждого преобразования есть fixtures до/после; неизвестная версия не принимается молча.

Изменение discriminator/kind существующего материала — отдельный use case с проверкой status, версии и допустимости преобразования, не независимое редактирование двух полей. Изменение JSON shape без schema bump и migration plan запрещено. Backup/export и image rollback проверяются на совместимость; downgrade кода не откатывает JSON-данные автоматически.

В 0.2 остаётся простая модель плана без преждевременного payload; envelope/constraints добавляются миграцией вместе с редакцией 0.4. На 0.2 всё равно действуют enums, роли, state transitions и единственная application-граница записи.

#### Внешние эффекты и приёмка

Пример `match` фиксирует намерения в той же транзакции, не вызывает Telegram/VK/GitHub. Сборка/подтверждение выкладки — [ADR 0008](0008-db-source-of-truth.md); delivery outbox — [ADR 0012](0012-reliable-external-effects.md). Анонсы 0.3 идут из выложенного RSS, не из любого ORM save. Кросспостинг материалов вне сайта остаётся поздней возможностью PRD.

Проверки будущей реализации: tag mismatch, отсутствующий/null envelope, неизвестная версия, неверные data types, invalid URL, version другого Content, race двух редакторов, rollback без внешнего эффекта, намеренная некорректная SQL-запись отклоняется DB constraints. Отдельно проверить data migration и чтение старой/new версии, DMR error mapping без утечки JSON/ORM internals.

## Альтернативы

* **Отдельная модель на каждый тип (`Article`, `Video`, `Podcast`) без общей сущности:**
  * *Плюсы:* каждая модель простая и самостоятельная, нет JSON.
  * *Минусы:* панели контент-плана нужен единый список всех материалов со сроками и статусами. Пришлось бы склеивать несколько таблиц или дублировать поля планирования. Новый тип требует правок во всех местах, где строится общий список.

* **Наследование моделей Django (multi-table inheritance):**
  * *Плюсы:* общий базовый класс, ORM-поддержка из коробки.
  * *Минусы:* JOIN на каждый запрос к конкретному типу, неочевидное поведение при выборках по базовому классу, тянет к наследованию вместо композиции (против манифеста).

* **Одна таблица с nullable-колонками под все типы (`embed_url`, `audio_url`, `body`…):**
  * *Плюсы:* просто, всё запрашивается SQL.
  * *Минусы:* при каждом новом типе таблица разрастается, инварианты («у видео обязательна ссылка») проверяются вручную, легко получить статью с `embed_url`. Primitive Obsession никуда не девается.

* **JSON payload без типизированных объектов (`dict` по всему коду):**
  * *Плюсы:* минимум кода на старте.
  * *Минусы:* опечатки в ключах, нет валидации, правила по типу расползаются по сервисам в виде `if kind == ...`. Именно то, от чего это решение защищает.

* **Полиморфизм через подклассы `Content` (Python-наследование без Django multi-table):**
  * *Плюсы:* методы по типу живут в подклассах.
  * *Минусы:* с Django-моделями требует proxy-моделей и фабрик при загрузке. Tagged union с `match` и проверкой исчерпывающей обработки даёт то же самое проще и надёжнее.

## Последствия

### Положительные

* [+] Единый список материалов всех типов для панели контент-плана и очереди редактора.
* [+] Правила типа инкапсулированы в payload, сервисы не ветвятся по строкам.
* [+] Новый тип — новый payload и ветка в `match`, а тайпчекер укажет, где её не хватает.
* [+] Нет Primitive Obsession: тип, срок, slug, ссылка на видео — типизированные объекты с валидацией.
* [+] Композиция вместо наследования, в духе архитектурного манифеста.
* [+] Поэтапное внедрение: в 0.2 модель простая, сложность появляется вместе с реальной потребностью.

### Отрицательные

* [-] Данные payload в JSON: по ним неудобно фильтровать и индексировать в SQL (при необходимости — индексы по выражениям PostgreSQL).
* [-] Нужен слой сериализации JSON ↔ VO и миграции данных при изменении структуры payload.
* [-] Структурную согласованность защищают PostgreSQL constraints, но сложные инварианты и JSON-ссылки всё равно требуют model/service validation и проверенных путей записи.
* [-] Команде нужно понимать tagged union и `match`, это нужно объяснить в архитектурном манифесте.

## Ссылки

* [PEP 634 — Structural Pattern Matching](https://peps.python.org/pep-0634/)
* [typing.assert_never](https://docs.python.org/3/library/typing.html#typing.assert_never)
* [Django: JSONField](https://docs.djangoproject.com/en/stable/ref/models/fields/#jsonfield)
* [msgspec](https://jcristharif.com/msgspec/)
* Архитектурный манифест (Pragmatic DDD, композиция вместо наследования)
* ADR 0004, ADR 0008


* [ADR 0004 — DMR/application services](0004-micro-cms-django-react.md), [ADR 0011 — DI и модели](0011-application-architecture-and-boundaries.md), [ADR 0014 — public contract](0014-cross-stack-content-contract.md).
* [Django: model validation не вызывается автоматически save](https://docs.djangoproject.com/en/5.2/ref/models/instances/#validating-objects), [QuerySet bulk/update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/).
