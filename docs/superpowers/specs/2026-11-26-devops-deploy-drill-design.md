# DevOps deploy drill — design spec

> Статус: Approved 26.11.2026  
> Ветка: `devops/chaos-self-heal`  
> Область: только DevOps; новый PR и push не создаются без отдельной команды.

## Контекст и цель

После слияния Astro-сайта и введения контракта артефакта (`stage-site`, `check-site-artifact`) цепочка выкладки стала проверяемой статически, но не имеет локального сквозного прогона. Настоящая выкладка заблокирована Q-1 (адрес) и `ENABLE_DEPLOY`, поэтому ошибки в `deploy-static.sh`, подписи, smoke и откате могут проявиться только после включения гейтов.

Цель — добавить воспроизводимую локальную репетицию всей цепочки на временных данных: сборка → нормализация артефакта → хэш/подпись → атомарная выкладка → smoke → откат. Никаких прод-ресурсов, адресов, секретов и гейтов.

## Вне границ

- `serv`, личный сервер пользователя, не используется.
- `/srv/sreda/**`, systemd, Caddy, Grafana, Loki и другие чужие процессы не трогаются.
- `apps/site/**`, `.github/workflows/ci.yml`, `scripts/check_log_schema.py` не изменяются.
- `404.html` не создаётся и не коммитится: issue #5 остаётся зоной фронтенда.
- `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL` не задаются.
- Обязательный статус `ci` и список рецептов в `verify` не меняются.
- Реальные cosign/OIDC, gh API и внешние запросы не используются.

## Архитектура

Источник правды — уже существующие скрипты: `scripts/stage-site.sh`, `scripts/check_site_artifact.py`, `scripts/sign-artifact.sh`, `scripts/verify-artifact.sh`, `scripts/deploy-static.sh`, `scripts/smoke-static.sh`. Новый оркестратор только вызывает их в нужном порядке и подготавливает временные каталоги.

```text
build-site → stage-site → (временная копия dist + учебная 404)
           → sign-artifact → verify-artifact
           → deploy-static.sh deploy ×2 → smoke-static.sh
           → deploy-static.sh rollback → проверка симлинка → cleanup
```

Каждый шаг пишет только во временный каталог `mktemp -d`. `trap` останавливает локальный HTTP-сервер и удаляет временные файлы при любом выходе.

## Компоненты

### `scripts/deploy-drill.sh` (новый, executable)

- Определяет `REPO_ROOT` из расположения скрипта и `cd` в него.
- Команду `just` берёт из переменной `JUST` с значением по умолчанию `uvx --from rust-just just`; это нужно, потому что локальный `just` не установлен.
- Проверяет наличие `pnpm` и запускает `pnpm install --frozen-lockfile`, чтобы чистое окружение могло собрать Astro.
- Выполняет `$JUST build-site` и `$JUST stage-site`. Реальный `dist/` в репозитории не является источником для выкладки: drill копирует его в `$TMP/artifact`.
- Создаёт в `$TMP/artifact/404.html` учебную заглушку с явным сообщением в stdout: это не исправление issue #5 и файл не попадает в git.
- Вызывает `$REPO_ROOT/scripts/sign-artifact.sh "$TMP/artifact"` и `$REPO_ROOT/scripts/verify-artifact.sh "$TMP/artifact"`. Без cosign подпись честно пропускается, хэш проверяется всегда.
- Создаёт вторую версию артефакта `$TMP/artifact-v2` с файлом-маркером, чтобы у `deploy-static.sh` был предыдущий релиз для отката.
- Дважды вызывает `$REPO_ROOT/scripts/deploy-static.sh deploy ...` с каталогом `$TMP/releases` и симлинком `$TMP/current`. Прод-пути не используются.
- Поднимает `python3 -m http.server` на свободном порту `127.0.0.1`, дожидается готовности через `curl --retry` и вызывает `$REPO_ROOT/scripts/smoke-static.sh "http://127.0.0.1:$PORT"`. Маркер контента не задаётся: проверяются только 200 на главной и 404 на несуществующей странице.
- Вызывает `$REPO_ROOT/scripts/deploy-static.sh rollback "$TMP/releases" "$TMP/current"` и проверяет, что симлинк указывает на первый релиз и там есть `index.html`.
- Печатает короткий итог с путями временных каталогов и явным сообщением, что прод не тронут. Любая ошибка → `FAIL:` в stderr и exit 1.

### Рецепт `just deploy-drill`

Добавляется в конец `justfile` после `check-site-artifact`. Не входит в `verify` и не упоминается в `ci`.

### `.github/workflows/deploy-drill.yml` (новый, неблокирующий)

- Триггеры: `workflow_dispatch` и `pull_request` с путями `scripts/deploy-drill.sh`, `scripts/deploy-static.sh`, `scripts/stage-site.sh`, `scripts/sign-artifact.sh`, `scripts/verify-artifact.sh`, `justfile`, сам workflow.
- `permissions: contents: read`; checkout `actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0` с `persist-credentials: false`.
- Setup pnpm `pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115 # v6.1.1`, setup Node `actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0` с `node-version: '22.23.2'` и `cache: pnpm`, `pnpm install --frozen-lockfile`.
- Composite `.github/actions/setup-just` с комментарием `zizmor: ignore[self-repository]`, затем `just deploy-drill`.
- Задание `continue-on-error: true`: репетиция не становится новым обязательным статусом и не мешает чужим PR.

### Документация

- `docs/runbook.md`: короткий раздел «Локальная репетиция выкладки» с командой, пояснением про учебную 404 и явной оговоркой, что прод не трогается.
- `docs/DEVOPS-STATUS.md`: одна строка в таблице проверок и строка в «Подготовлено, но не включено» с пометкой, что drill не выкладывает на реальный адрес.
- `CONTRIBUTING.md`: рецепт `just deploy-drill` в списке неблокирующих локальных проверок.

## Обработка ошибок

- Нет `pnpm`/`apps/site/dist` или упала сборка — drill падает с явным сообщением, не создавая прод-артефакт.
- Отсутствует `dist/index.html` — падает на этапе подготовки артефакта.
- Хэш не совпал — `verify-artifact.sh` возвращает ненулевой код, drill останавливается до выкладки.
- Smoke не прошёл — drill останавливается, временный каталог удаляется trap'ом, rollback не выполняется автоматически: репетиция показывает проблему, а не маскирует её.
- Откат не смог переключить симлинк — FAIL, temporary cleanup выполняется.
- `curl`/`python3` недоступны — FAIL с сообщением, без попытки обратиться к сети.

## Тестирование

Локально на текущем checkout:

```bash
bash -n scripts/deploy-drill.sh
uvx --from rust-just just deploy-drill
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
uv run --with pyyaml==6.0.4 python scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
python3 scripts/check_commit_messages.py
git diff --check
```

Ожидаемые признаки успеха: реальный `$ astro build`, Prepared SHA256, `verify-artifact` с целым хэшем, `deploy` дважды, `smoke` с `главная=200, отсутствующая=404`, rollback с переключением на первый релиз, пустой `git status` и отсутствие новых файлов в `/srv/sreda`.

Дополнительно: `scripts/workflows_lint.sh` (actionlint 0, zizmor No findings) и `mkdocs build --strict`. Полный `just verify` не изменяет обязательный набор проверок и должен остаться зелёным.

## Связь с замечаниями Ильи

- Не делается фиктивная заглушка вместо реальной проверки: drill запускает настоящие скрипты выкладки и smoke на локальном HTTP-сервере.
- Никаких прода-секретов, `/srv`, гейтов и алертов.
- Новый workflow неблокирующий и не переименовывает обязательный `ci`.
- YAML для `run:` пишется безопасной строкой без ` #` посередине, чтобы shellcheck в CI не ловил незакрытую кавычку.
