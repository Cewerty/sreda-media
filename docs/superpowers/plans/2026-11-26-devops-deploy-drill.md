# Deploy Drill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить воспроизводимую локальную репетицию всей цепочки выкладки статического артефакта без прода, адресов и гейтов.

**Architecture:** Оркестратор `scripts/deploy-drill.sh` вызывает уже существующие скрипты сборки, нормализации, подписи, выкладки и smoke во временном каталоге. Рецепт `just deploy-drill` и неблокирующий workflow дают проверяемость на чистом checkout; обязательный `ci` и гейты не меняются.

**Tech Stack:** Bash, Python 3 stdlib, pnpm, Astro, GitHub Actions, `uvx --from rust-just just`, mktemp, local `python3 -m http.server`.

---

### Task 1: Local deploy drill script and recipe

**Files:**
- Create: `scripts/deploy-drill.sh`
- Modify: `justfile` (append recipe after `check-site-artifact`)

- [ ] **Step 1: Write the script exactly as follows**

`scripts/deploy-drill.sh`:

```bash
#!/usr/bin/env bash
# Сквозная локальная репетиция выкладки статического артефакта (issue #7, ADR 0015).
#
#   scripts/deploy-drill.sh
#
# Прогоняет build-site -> stage-site -> sign/verify -> deploy x2 -> smoke -> rollback
# только во временном каталоге. Не трогает /srv, systemd, прод-адрес и ENABLE_*.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '[deploy-drill] %s\n' "$*"; }
fail() { printf '[deploy-drill] FAIL: %s\n' "$*" >&2; exit 1; }

read -r -a JUST_CMD <<< "${JUST:-uvx --from rust-just just}"

command -v pnpm >/dev/null 2>&1 || fail "pnpm не найден: нужна среда Node/pnpm"
command -v python3 >/dev/null 2>&1 || fail "python3 не найден"
command -v curl >/dev/null 2>&1 || fail "curl не найден"
[ -d apps/site ] || fail "apps/site отсутствует"
[ -f apps/site/package.json ] || fail "apps/site/package.json отсутствует"

TMP=$(mktemp -d)
HTTP_PID=""
cleanup() {
    if [ -n "$HTTP_PID" ]; then
        kill "$HTTP_PID" >/dev/null 2>&1 || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT

pnpm install --frozen-lockfile
"${JUST_CMD[@]}" build-site
"${JUST_CMD[@]}" stage-site
[ -f dist/index.html ] || fail "dist/index.html не создан stage-site"

ARTIFACT="$TMP/artifact"
mkdir -p "$ARTIFACT"
cp -a dist/. "$ARTIFACT/"
# Учебная заглушка: issue #5 остаётся зоной фронтенда, в git файл не попадает.
printf '<html><body>404</body></html>\n' > "$ARTIFACT/404.html"
log "создана учебная 404.html во временном артефакте (issue #5, не коммитится)"

"$REPO_ROOT/scripts/sign-artifact.sh" "$ARTIFACT"
"$REPO_ROOT/scripts/verify-artifact.sh" "$ARTIFACT"

RELEASES="$TMP/releases"
CURRENT="$TMP/current"
ARTIFACT_V2="$TMP/artifact-v2"
mkdir -p "$ARTIFACT_V2"
cp -a "$ARTIFACT/." "$ARTIFACT_V2/"
printf 'deploy drill v2\n' > "$ARTIFACT_V2/drill-v2.txt"

"$REPO_ROOT/scripts/deploy-static.sh" deploy "$ARTIFACT" "$RELEASES" "$CURRENT"
sleep 1
"$REPO_ROOT/scripts/deploy-static.sh" deploy "$ARTIFACT_V2" "$RELEASES" "$CURRENT"
[ -L "$CURRENT" ] || fail "current не является симлинком"

PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 -m http.server "$PORT" --directory "$CURRENT" >"$TMP/http.log" 2>&1 &
HTTP_PID=$!
curl --retry 10 --retry-connrefused --retry-delay 1 -fsS "http://127.0.0.1:$PORT/" >/dev/null
env -u SREDA_SMOKE_MARKER "$REPO_ROOT/scripts/smoke-static.sh" "http://127.0.0.1:$PORT"
kill "$HTTP_PID" >/dev/null 2>&1 || true
HTTP_PID=""

FIRST_RELEASE=$(cat "$RELEASES/.previous")
"$REPO_ROOT/scripts/deploy-static.sh" rollback "$RELEASES" "$CURRENT"
[ "$(readlink "$CURRENT")" = "$FIRST_RELEASE" ] || fail "откат не вернул первый релиз"
[ -f "$CURRENT/index.html" ] || fail "после отката нет index.html"

log "успешно: сборка, подпись, две выкладки, smoke и откат во временном каталоге"
log "прод-пути, гейты и внешние сервисы не использовались; временные файлы удаляются"
```

Make it executable:

```bash
chmod +x scripts/deploy-drill.sh
```

- [ ] **Step 2: Add the just recipe**

Append to the end of `justfile` after `check-site-artifact`:

```just
# Сквозная локальная репетиция выкладки, без прода и гейтов; вне verify и CI.
deploy-drill:
    ./scripts/deploy-drill.sh
```

Verify that `verify` at the top of `justfile` is unchanged and does not contain `deploy-drill`.

- [ ] **Step 3: Verify syntax and static checks**

```bash
bash -n scripts/deploy-drill.sh
uvx --from rust-just just --list
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
uv run --with pyyaml==6.0.4 python scripts/check_runbook_commands.py
git diff --check
```

Expected: all exit 0; `deploy-drill` is listed but absent from `verify`.

- [ ] **Step 4: Run the drill on the real checkout**

```bash
uvx --from rust-just just deploy-drill
```

Expected: real `$ astro build`, `[sign] SHA256 подготовлен`, `[verify-artifact] SHA256 корректен`, two `[deploy] развёрнут ...` lines with different UTC stamps, `[smoke] главная=200, отсутствующая=404`, `[deploy] откат выполнен`, then the final success lines. `git status --short` must remain clean except for the two intended files; no `404.html` appears in `git ls-files`; nothing under `/srv/sreda` changes.

- [ ] **Step 5: Commit**

```bash
git add scripts/deploy-drill.sh justfile
git commit -F- <<'MSG'
chore(devops): add local deploy drill

Добавлена сквозная локальная репетиция выкладки без прода, адресов и гейтов.
Новый PR и push не создавались, serv и чужие ветки не трогались.

Скрипт scripts/deploy-drill.sh вызывает уже существующие build-site, stage-site,
sign-artifact, verify-artifact, deploy-static (deploy ×2 и rollback) и
smoke-static. Всё выполняется в mktemp -d; локальный HTTP-сервер поднимается
на свободном порту 127.0.0.1. Для проекта deploy-static создаются две версии
артефакта, чтобы проверить и выкладку, и откат. Учебная 404.html создаётся
только во временном артефакте: issue #5 остаётся зоной фронтенда.

Рецепт just deploy-drill добавлен в конец justfile и не входит в verify или ci.

Проверки: bash -n, just --list, check.py, config_lint.py, check_links.py,
check_runbook_commands.py, git diff --check; реальный прогон с Astro-сборкой
показал 200/404, две выкладки и успешный откат. Прод-пути, ENABLE_* и алерты
не трогались.

Refs: #5 #9 #14 #47 #48
MSG
```

If `/tmp` is out of space, use several `git commit -m` arguments with the same subject/body instead of a heredoc.

---

### Task 2: Non-blocking deploy drill workflow

**Files:**
- Create: `.github/workflows/deploy-drill.yml`

- [ ] **Step 1: Write the workflow exactly as follows**

```yaml
name: Deploy drill (non-blocking)

# Сквозная локальная репетиция выкладки на чистом runner.
# Не входит в обязательный ci, не публикует и не выкладывает артефакт.
on:
  workflow_dispatch:
  pull_request:
    paths:
      - scripts/deploy-drill.sh
      - scripts/deploy-static.sh
      - scripts/stage-site.sh
      - scripts/sign-artifact.sh
      - scripts/verify-artifact.sh
      - justfile
      - .github/workflows/deploy-drill.yml

permissions:
  contents: read

jobs:
  drill:
    name: Local deploy rehearsal
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - name: Checkout
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
      - name: Setup pnpm
        uses: pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115 # v6.1.1
      - name: Setup Node
        uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        with:
          node-version: '22.23.2'
          cache: pnpm
      - name: Install JS dependencies
        run: pnpm install --frozen-lockfile
      - name: Setup just
        uses: ./.github/actions/setup-just # zizmor: ignore[self-repository]
      - name: Run deploy drill
        env:
          JUST: just
        run: just deploy-drill
```

- [ ] **Step 2: Verify workflow syntax and policy**

```bash
python3 scripts/config_lint.py
python3 scripts/check.py
python3 scripts/audit_workflows.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
uv run --with pyyaml==6.0.4 python scripts/check_runbook_commands.py
scripts/workflows_lint.sh
git diff --check
```

Expected: `config_lint.py` reports `workflow 23`; `audit_workflows.py` accepts the new local `./...` action; actionlint reports 0 errors; zizmor reports `No findings`. `continue-on-error` is present, so the job does not become a new required status.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-drill.yml
git commit -F- <<'MSG'
ci(devops): add non-blocking deploy drill workflow

Добавлен workflow deploy-drill.yml для проверки репетиции выкладки на чистом
runner. Триггеры: workflow_dispatch и pull_request только по затронутым путям.
Задание continue-on-error, обязательный статус ci и ruleset не меняются.

Workflow использует зафиксированные checkout/pnpm/setup-node по SHA, Node
22.23.2 с pnpm-кэшем, pnpm install --frozen-lockfile, composite setup-just и
just deploy-drill. Права только contents: read, persist-credentials: false.

Проверки: config_lint (workflow 23), check.py, audit_workflows, workflow
hardening, check_runbook_commands, actionlint 0 ошибок, zizmor No findings,
git diff --check. Прод-адрес, флаги ENABLE_*, секреты и алерты не трогались.

Refs: #9 #14 #26 #48
MSG
```

---

### Task 3: Document the drill and run final verification

**Files:**
- Modify: `CONTRIBUTING.md`
- Modify: `docs/DEVOPS-STATUS.md`
- Modify: `docs/runbook.md`

- [ ] **Step 1: Patch CONTRIBUTING.md**

Find this exact sentence:

```text
Выкладка готовится в `deploy.yml`, но не выполняется без `ENABLE_DEPLOY=true` и явного `dry_run=false`; smoke после выкладки — `just smoke <url>` с необязательным `SREDA_SMOKE_MARKER`.
```

Replace with:

```text
Выкладка готовится в `deploy.yml`, но не выполняется без `ENABLE_DEPLOY=true` и явного `dry_run=false`; smoke после выкладки — `just smoke <url>` с необязательным `SREDA_SMOKE_MARKER`. Сквозная локальная репетиция без прода — `just deploy-drill`: сборка, нормализация артефакта, хэш/подпись, две выкладки во временном каталоге, smoke и откат; рецепт не входит в `verify` и `ci`.
```

- [ ] **Step 2: Patch docs/DEVOPS-STATUS.md**

Find this exact table row:

```markdown
| `release-readiness` | Вручную, вне `verify` и CI | Таблица готовности с вердиктом `READY`/`NO-GO`; ничего не включает. |
```

Replace with the same row plus one new row immediately after it:

```markdown
| `release-readiness` | Вручную, вне `verify` и CI | Таблица готовности с вердиктом `READY`/`NO-GO`; ничего не включает. |
| `deploy-drill` | Отдельно, dispatch + PR paths | Полная локальная репетиция выкладки во временном каталоге, без `/srv` и гейтов. |
```

Find this exact row in «Подготовлено, но не включено»:

```markdown
| Манифест релиза | Готов как рецепт, но не входит в CI | `just release-manifest dist` после появления артефакта |
```

Replace with the same row plus one new row immediately after it:

```markdown
| Манифест релиза | Готов как рецепт, но не входит в CI | `just release-manifest dist` после появления артефакта |
| `deploy-drill` | Репетиция не выкладывает на реальный адрес и не трогает прод | `just deploy-drill` локально; в CI — dispatch или PR по затронутым путям |
```

- [ ] **Step 3: Patch docs/runbook.md**

Append to the end of the section «Учебные репетиции» after the `sre-digest` paragraph:

```markdown
`just deploy-drill` — сквозная локальная репетиция выкладки: `build-site`, `stage-site`, подготовка хэша/подписи, две выкладки во временном каталоге, smoke на локальном HTTP-сервере и откат. Она создаёт учебную `404.html` только во временном артефакте, не трогает `/srv`, `ENABLE_DEPLOY` и реальный адрес, поэтому issue #5 остаётся открытой. Неблокирующий workflow `deploy-drill.yml` повторяет ту же репетицию на чистом runner.
```

- [ ] **Step 4: Run all static checks**

```bash
python3 -m py_compile scripts/*.py
bash -n scripts/*.sh
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
python3 scripts/check_log_schema.py
uv run --with pyyaml==6.0.4 python scripts/check_runbook_commands.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
python3 scripts/audit_workflows.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
scripts/workflows_lint.sh
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /home/deb/mkdocs-deploy-drill
python3 scripts/check_commit_messages.py
git diff --check
```

Expected: all exit 0; actionlint 0 errors; zizmor `No findings`; all 10 alert rules still `enabled=false`; no `404.html` tracked.

- [ ] **Step 5: Run full verify**

```bash
uvx --from rust-just just api-db-up
trap 'uvx --from rust-just just api-db-down >/dev/null 2>&1 || true' EXIT
uvx --from rust-just just verify 2>&1 | tee /home/deb/just-verify-deploy-drill.log | tail -30
```

Expected: log ends with `just verify: все проверки пройдены`; PostgreSQL container is stopped by the trap. `deploy-drill` is not part of `verify`, so the same checks as before must pass.

- [ ] **Step 6: Commit**

```bash
git add CONTRIBUTING.md docs/DEVOPS-STATUS.md docs/runbook.md
git commit -F- <<'MSG'
docs: reflect deploy drill in ops docs

Документирована локальная сквозная репетиция выкладки. Новый PR и push не
создавались, serv и чужие ветки не трогались.

CONTRIBUTING.md: добавлен рецепт just deploy-drill в список неблокирующих
локальных проверок с явным указанием, что он не входит в verify и ci.
docs/DEVOPS-STATUS.md: одна строка в таблице проверок и строка в разделе
«Подготовлено, но не включено» с пометкой, что drill не выкладывает на
реальный адрес. docs/runbook.md: раздел «Учебные репетиции» дополнен
описанием полного цикла и учебной 404.html, issue #5 остаётся открытой.

Проверки: py_compile, bash -n, check.py, config_lint.py, check_links.py,
check_log_schema.py, check_runbook_commands.py, check_alert_rules.py,
check_alert_runbooks.py, audit_workflows.py, workflow hardening, actionlint 0,
zizmor No findings, mkdocs build --strict, check_commit_messages.py,
git diff --check; полный just verify с PostgreSQL 18 на 127.0.0.1:55432
зелёный, лог /home/deb/just-verify-deploy-drill.log.

Refs: #5 #9 #14 #47 #48
MSG
```

---

**Final handoff:** after Task 3, run one final integration review of the whole range and report to the owner. Do not push and do not open a PR without an explicit command.
