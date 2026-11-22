# ADR 0008: БД микро-CMS — источник правды для контента; сайт собирается из API CMS

## Дата: 20-11-2026

## Статус: Accepted

Принято владельцем проекта 22-11-2026.

Актуализация: 21-11-2026. Уточнены DMR snapshot API, deployment state, ошибки сборки и recovery.

Заменяет: ADR 0003

## Контекст

ADR 0003 сделал источником правды Git: CMS открывала PR со статьями через GitHub API, редактор смотрел превью-деплой, merge публиковал статью. Это решение осталось от ранней схемы, в которой своей CMS ещё не было и статьи жили в репозитории.

С появлением своей микро-CMS с PostgreSQL (ADR 0004) у этой схемы проявились недостатки:

- **Двойное состояние.** Статус статьи хранится в базе, а состояние PR — в GitHub. Их нужно синхронизировать, расхождения неизбежны (PR закрыли руками, merge упал, ветку удалили).
- **Сложная интеграция.** Ветки, коммиты, PR, merge через GitHub API, фоновые задачи с повторами, токен с правами записи в репозиторий.
- **Монорепозиторий (ADR 0007).** PR со статьями смешиваются с PR кода. Нужны CODEOWNERS, ограничения токена и отдельный job в CI, который проверяет, что CMS не трогает код.
- **Инфраструктура превью.** Wildcard DNS, TLS для поддоменов `pr-<N>`, очистка превью.

База данных в системе есть в любом случае, поэтому хранить контент ещё и в Git означает держать вторую копию.

## Решение

Принято решение **сделать базу данных микро-CMS единственным источником правды для материалов**, а **сайт собирать статически, забирая опубликованные статьи из API CMS во время сборки**, потому что:

- состояние статьи живёт в одном месте, в одной машине состояний;
- вместо интеграции с GitHub API нужен только вызов «пересобери сайт»;
- сайт остаётся статическим (ADR 0001): читатель получает готовый HTML, к базе в рантайме никто не обращается;
- риск «CMS умерла, контент заперт в базе» закрывается регулярным экспортом в `.md`.

### Детали реализации

#### 1. БД и два состояния публикации

PostgreSQL хранит материалы, версии, редакционные статусы, заметки, авторские профили и ссылки на медиа; бинарные файлы находятся в private storage. Application services и транзакции определены [ADR 0004](0004-micro-cms-django-react.md), DI — [ADR 0011](0011-application-architecture-and-boundaries.md).

`Content.status=published` означает включение конкретной проверенной версии в желаемый public dataset, не подтверждение доступности нового HTML. Build-состояния не добавляются в editorial state machine. Отдельная `PublicationDeployment` учитывает desired revision, snapshot ID, correlation/request ID, workflow run ID при получении, outcome, deployed revision и время подтверждения.

UI различает «принято / сборка ожидает / ошибка / выложено». Build failure не отменяет одобрение и не выдаётся за успешный deploy. Редакционный процесс не синхронизируется с состоянием PR.

#### 2. DMR read-only snapshot API

- Выделенные DMR controllers под `/api/build/` выдают public contract, не обычный CMS CRUD с фильтром.
- `PublishedSnapshotService` внедряется Dishka. Отдельный read-only build token не даёт доступа к draft/identities/write; он доступен только CI/server, не браузеру.
- Typed response schemas DMR фиксируются в OpenAPI и сверяются с [ADR 0014](0014-cross-stack-content-contract.md). Валидация формы не заменяет snapshot isolation.
- Immutable manifest содержит schema version, snapshot ID, UTC timestamp, dataset revision, public материалы/рубрики/авторов и media checksums. При пагинации все страницы читают один snapshot, не разные состояния live queryset.
- Передаётся Markdown выбранной published version, не latest draft. Telegram/provider IDs, private deadlines/notes и роли не попадают в API/export.
- Snapshot создаётся из согласованного состояния БД. Version/media references не меняются in-place; очистка snapshots учитывает работающие workflow и текущую выкладку.

#### 3. Astro loader, assets и preview

Loader преобразует snapshot в ту же нормализованную модель, что файлы MVP. Schema, ссылки, директивы и media checksums проверяются до выкладки. Ошибка не портит текущий release.

Обложки, картинки статьи и нужные изображения профилей входят в build. CMS не требуется для их runtime-загрузки. Внешние video/audio embeds остаются внешними по PRD; видео не копируется в media storage.

Preview использует общие remark-плагины, стили и validator ADR 0002/0014. Совпадает область статьи, не шапка/навигация всего сайта.

#### 4. Build intent и failure semantics

В одной application-транзакции сохраняются published version, desired revision, audit и outbox build intent. После commit worker вызывает `SiteBuildPort` → GitHub adapter. Controller/model не запускают SDK напрямую.

Worker схлопывает близкие запросы до актуальной desired revision. GitHub `concurrency` ограничивает конкурентные deploy, но не заменяет debounce/durable state. Если цель меняется во время build, нужна завершающая сборка актуального snapshot.

`workflow_dispatch` подтверждает запрос, не deploy. Timeout даёт неизвестный исход и требует сверки по correlation ID. Результат подтверждается аутентифицированным callback или workflow + публичным deployment manifest. Старый job не может переключить сайт поверх новой ревизии: актуальность проверяется перед atomic release switch.

Failed/cancelled/invalid build оставляет прошлые HTML/assets. CMS показывает отставание и safe failure; повтор той же ревизии безопасен. Workflow не редактирует live release по одному файлу.

Токен CMS не получает `Contents: write`; repo/workflow/ref фиксированы. Минимальное `Actions: write` для dispatch шире «только один workflow»: остаточный риск по NFR-SEC-04 согласуется явно. При строгой capability нужен отдельный ограниченный dispatcher, не неверное описание GitHub permissions.

#### 5. Ночной export format

Завершённый архив содержит `.md` с frontmatter, public author/rubric справочники, локальные media и manifest с schema/snapshot revision, составом, UTC timestamp и checksums. Формат/stable IDs совпадают с файловым MVP и ADR 0014.

Экспорт сначала валидируется во временной области, затем атомарно помечается завершённым. Неполный архив не заменяет последнюю пригодную копию. Архив хранится рядом с backup sets и копируется вне VPS по ADR 0015.

Published export не содержит аккаунты, все черновики/версии и outbox; он не заменяет backup PostgreSQL + media. Его задача — позволить собрать витрину без CMS.

#### 6. Recovery drill

Ежедневный backup обязателен с появлением stateful данных; до 0.4 проверяется восстановление. Retention/внешняя копия — [ADR 0015](0015-runtime-and-data-operations.md).

Два сценария проверяются отдельно:

1. **Вернуть CMS:** остановить writers/worker, восстановить DB + media, проверить schema/контрольные данные и сверить restored outbox с внешними площадками до возобновления delivery.
2. **Уйти от CMS:** проверить completed export/checksums, собрать Astro file loader при отключённой CMS, открыть статьи/рубрики/авторов/картинки/RSS.

Отчёт drill фиксирует backup/export ID, tool versions, длительность, результат и operator steps. Наличие dump не считается проверкой восстановления.

### Этапы

По итогам опроса главы медийки (20-11-2026) материалы выходят раз в 1,5–2 недели, авторов около трёх. Для запуска CMS не нужна.

1. **MVP.** Статьи и видео хранятся файлами в `apps/site/src/content/`, в **том же формате, что и ночной экспорт** (п. 8 выше): `.md` с frontmatter и медиа рядом. Сайт собирается стандартным `glob`-загрузчиком. Материалы в репозиторий добавляют разработчики по тексту от редакции.
2. **Второй этап.** Запускается микро-CMS (ADR 0004). Файлы из MVP импортируются в базу, `glob`-загрузчик заменяется загрузчиком из API. Схема коллекций остаётся прежней, поэтому шаблоны и страницы сайта не меняются.

Поскольку формат MVP совпадает с форматом экспорта, путь «CMS умерла → вернуться к файлам» — это тот же первый этап в обратную сторону, и он проверяется уже на старте.

## Альтернативы

* **Git — источник правды, CMS открывает PR (ADR 0003):**
  * *Плюсы:* история, ревью и откат бесплатно средствами Git. Контент переживает смерть CMS без дополнительных мер, статьи можно коммитить руками.
  * *Минусы:* двойное состояние (база и PR), сложная интеграция с GitHub API, токен с правами записи в репозиторий, шум в монорепозитории, инфраструктура превью на каждый PR. Главный плюс (живучесть контента) достигается экспортом-страховкой дешевле.

* **Сайт читает API CMS в рантайме (SSR или headless) + кэш в Redis (например, cashews):**
  * *Плюсы:* публикация мгновенная, пересборка не нужна.
  * *Минусы:* сайт зависит от доступности CMS, нужен Redis — ещё один сервис в эксплуатации (против духа ADR 0005). По сути это headless-схема, отвергнутая в ADR 0001. При статической сборке кэшировать нечего: в рантайме к базе никто не обращается.

* **Двусторонняя синхронизация базы и Git:**
  * *Плюсы:* правки можно вносить и там, и там.
  * *Минусы:* конфликты, рассинхронизация, сложная логика. Неоправданно для проекта такого масштаба.

## Последствия

### Положительные

* [+] Одна машина состояний статьи, синхронизировать нечего.
* [+] Интеграция с GitHub сводится к одному вызову `workflow_dispatch`, токен не может менять код.
* [+] Монорепозиторий содержит только код: нет PR со статьями, CODEOWNERS для контента и ограничений токена (ADR 0007 упрощается).
* [+] DevOps не нужны превью-деплои на каждую статью: wildcard DNS и on-demand TLS становятся необязательными.
* [+] Сайт по-прежнему статический и работает, даже если CMS лежит.

### Отрицательные

* [-] Если CMS недоступна, новые статьи не публикуются (сайт продолжает отдавать последнюю сборку).
* [-] Контент живёт только в базе: бэкапы и их проверка становятся критичными.
* [-] Историю и откат нужно реализовать самим (модель версий).
* [-] Превью в CMS приближённое: стили статьи общие, но обвязка сайта (шапка, навигация) не показывается.
* [-] Экспорт-страховку нужно поддерживать и периодически проверять, что из него действительно собирается сайт.

## Ссылки

* [Astro: Content Loader API](https://docs.astro.build/en/reference/content-loader-reference/)
* [GitHub Actions: workflow_dispatch](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#workflow_dispatch)
* [GitHub Actions: concurrency](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/control-the-concurrency-of-workflows-and-jobs)
* ADR 0001, ADR 0002, ADR 0003 (заменён), ADR 0004, ADR 0005, ADR 0007


* Уточнения: [ADR 0012 — delivery/deploy](0012-reliable-external-effects.md), [ADR 0014 — content contract](0014-cross-stack-content-contract.md), [ADR 0015 — recovery](0015-runtime-and-data-operations.md).
* [GitHub: фактические permissions workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event).
