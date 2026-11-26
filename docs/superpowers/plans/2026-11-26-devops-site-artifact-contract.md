# DevOps Site Artifact Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Нормализовать вывод реальной Astro-сборки в корневой `dist` и проверить контракт артефакта перед подписью и gated deploy, не меняя фронтенд и не включая прод-гейты.

**Architecture:** `just build-site` остаётся авторитетной сборкой Ильи и пишет в `apps/site/dist`. Новый `stage-site` копирует результат в корневой `dist`; новый `check-site-artifact` проверяет `index.html` и `404.html`. Workflow `site-build`, `deploy` и `provenance` используют один и тот же подготовленный артефакт.

**Tech Stack:** bash, Python 3.14 stdlib, just, GitHub Actions, pnpm/Astro 6, Docker Compose для локальных репетиций.

**Constraints:** только локальная ветка `devops/chaos-self-heal`, уже перемотанная до `origin/main`; новый PR не создаётся; push не делается без отдельной команды пользователя; PR #16/#50, `apps/site/**`, `ci.yml`, `check_log_schema.py`, гейты `ENABLE_*` и алерты не трогаются; коммиты только с подробными телами.

---

### Task 1: Stage Astro output into root dist

**Files:**
- Create: `scripts/stage-site.sh`
- Modify: `justfile` (append recipe at the end after `sre-digest`)
- Test: локальные негативные и позитивные проверки на сгенерированном `apps/site/dist`

- [ ] **Step 1: Write the staging script**

Создай `scripts/stage-site.sh` с точным содержимым:

```bash
#!/usr/bin/env bash
# Нормализация артефакта Astro: apps/site/dist -> корневой dist.
# Не собирает сайт, не подписывает, не выкладывает и не трогает /srv.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SRC="apps/site/dist"
DST="dist"

fail() { printf '[stage-site] ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ -d "$SRC" ] || fail "нет каталога $SRC: сначала запустите just build-site"
[ -f "$SRC/index.html" ] || fail "в $SRC нет index.html"

if [ -L "$DST" ]; then
    fail "$DST — симлинк, удаление опасно"
fi

rm -rf "$DST"
mkdir -p "$DST"
cp -a "$SRC/." "$DST/"

count=$(find "$DST" -type f | wc -l)
printf '[stage-site] готово: %s -> %s (%s файлов)\n' "$SRC" "$DST" "$count"
```

- [ ] **Step 2: Make it executable and check syntax**

Run:

```bash
chmod +x scripts/stage-site.sh
bash -n scripts/stage-site.sh
```

Expected: exit 0, no output.

- [ ] **Step 3: Add just recipe**

Append to the end of `justfile`:

```just
# Нормализация вывода Astro в корневой dist для подписи и выкладки.
stage-site:
    bash scripts/stage-site.sh
```

- [ ] **Step 4: Позитивная проверка с реальной сборкой Astro**

Run:

```bash
pnpm install --frozen-lockfile
just build-site
just stage-site
test -f dist/index.html
```

Expected: `just stage-site` prints `[stage-site] готово: apps/site/dist -> dist (N файлов)`, `dist/index.html` exists.

- [ ] **Step 5: Негативные проверки**

Run:

```bash
set -euo pipefail
TMP=$(mktemp -d)

# 1) dist is a symlink
rm -rf dist
ln -s "$TMP/target" dist
set +e
bash scripts/stage-site.sh 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 1 ] && [ -L dist ] || exit 1
rm dist

# 2) source is missing
mkdir -p /home/deb/.cache/site-dist-backup
mv apps/site/dist /home/deb/.cache/site-dist-backup/dist
set +e
bash scripts/stage-site.sh 2>/dev/null
rc=$?
set -e
mv /home/deb/.cache/site-dist-backup/dist apps/site/dist
rmdir /home/deb/.cache/site-dist-backup
[ "$rc" -eq 1 ] || exit 1

just stage-site
rm -rf "$TMP"
```

Expected: both negative cases return rc=1 and the symlink remains untouched; final `just stage-site` restores a real `dist`.

- [ ] **Step 6: Static checks**

Run:

```bash
python3 scripts/check.py
python3 scripts/config_lint.py
uvx --from rust-just just --list >/dev/null
git diff --check
```

Expected: all exit 0.

- [ ] **Step 7: Commit**

Run:

```bash
git add scripts/stage-site.sh justfile
git commit -m 'chore(devops): stage Astro output into root dist' \
  -m 'Локальный DevOps-контракт артефакта в ветке devops/chaos-self-heal. PR не создаётся, push не делается, frontend-исходники не тронуты.' \
  -m 'После слияния PR #16 just build-site собирает Astro в apps/site/dist, а sign-artifact.sh, verify-artifact.sh, deploy-static.sh и deploy/provenance workflow ждут корневой dist. Добавлен scripts/stage-site.sh: проверяет apps/site/dist/index.html, отказывается работать с симлинком dist, пересоздаёт корневой dist и копирует туда результат сборки. just build-site не изменён — это авторитетная часть Ильи.' \
  -m 'Рецепт stage-site добавлен в конец justfile вне verify, чтобы не менять обязательный ci. Проверены позитив с реальной сборкой Astro и негативы: dist-симлинк и отсутствующий apps/site/dist.' \
  -m 'Refs: #5 #9 #14 #47 #48'
```

Expected: one commit with 2 files.

---

### Task 2: Check static artifact contract

**Files:**
- Create: `scripts/check_site_artifact.py`
- Modify: `justfile` (append recipe after `stage-site`)
- Test: positive with temporary `404.html`, negatives with missing/empty files and custom root

- [ ] **Step 1: Write the checker**

Create `scripts/check_site_artifact.py` with exact content:

```python
#!/usr/bin/env python3
"""Read-only проверка контракта корневого артефакта витрины."""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "dist"
errors: list[str] = []


def check_required(name: str) -> None:
    path = ARTIFACT / name
    if not path.is_file():
        if name == "404.html":
            errors.append("dist/404.html отсутствует: issue #5, страница 404 в зоне фронтенда")
        else:
            errors.append(f"dist/{name} отсутствует")
        return
    if path.stat().st_size == 0:
        errors.append(f"dist/{name} пустой")


if not ARTIFACT.is_dir():
    errors.append("нет каталога dist: сначала запустите just stage-site")
else:
    check_required("index.html")
    check_required("404.html")

if errors:
    for message in errors:
        print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)

print("ok: artifact contract — dist/index.html и dist/404.html на месте")
```

- [ ] **Step 2: Make it executable, compile, add recipe**

Run:

```bash
chmod +x scripts/check_site_artifact.py
python3 -m py_compile scripts/check_site_artifact.py
```

Append to the end of `justfile`:

```just
# Read-only проверка контракта артефакта; не входит в verify и ci.
check-site-artifact:
    python3 scripts/check_site_artifact.py
```

- [ ] **Step 3: Позитивная проверка с временным 404**

Run:

```bash
set -euo pipefail
just stage-site
rm -f dist/404.html
printf '<html>404</html>\n' > dist/404.html
python3 scripts/check_site_artifact.py
rm -f dist/404.html
```

Expected: `ok: artifact contract — dist/index.html и dist/404.html на месте`, exit 0. The temporary file is removed; do not add `404.html` to git.

- [ ] **Step 4: Негативные проверки**

Run:

```bash
set -euo pipefail

# 1) 404 missing
set +e
python3 scripts/check_site_artifact.py 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 1 ] || exit 1

# 2) empty dist
mv dist /home/deb/.cache/dist-backup
mkdir -p dist
set +e
python3 scripts/check_site_artifact.py 2>/dev/null
rc=$?
set -e
rm -rf dist
mv /home/deb/.cache/dist-backup dist
[ "$rc" -eq 1 ] || exit 1

# 3) custom root with empty index
TMP=$(mktemp -d)
mkdir -p "$TMP/dist"
: > "$TMP/dist/index.html"
set +e
python3 scripts/check_site_artifact.py "$TMP" 2>/dev/null
rc=$?
set -e
rm -rf "$TMP"
[ "$rc" -eq 1 ] || exit 1

just stage-site
```

Expected: all three cases return rc=1; final `just stage-site` restores a real `dist`.

- [ ] **Step 5: Static checks and commit**

Run:

```bash
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
python3 scripts/check_runbook_commands.py
uvx --from rust-just just --list >/dev/null
git diff --check
```

Expected: all exit 0. Note: `check_runbook_commands.py` already sees `just stage-site` in the spec and the recipe now exists; `just check-site-artifact` also exists.

Commit:

```bash
git add scripts/check_site_artifact.py justfile
git commit -m 'chore(devops): check static artifact contract' \
  -m 'Локальный read-only чекер артефакта витрины. PR не создаётся, push не делается, 404.html не добавляется: это зона issue #5 и фронтенда.' \
  -m 'scripts/check_site_artifact.py проверяет dist/index.html и dist/404.html, принимает опциональный корень для негативных тестов и печатает отдельное пояснение про issue #5, когда 404 отсутствует. Рецепт check-site-artifact добавлен в конец justfile и не входит в verify, чтобы обязательный ci не стал красным из-за открытой фронтенд-карточки.' \
  -m 'Проверены позитив с временным 404.html и негативы: нет 404, пустой dist, пустой index.html в кастомном root. check.py, config_lint, check_links, check_runbook_commands, just --list и diff --check зелёные.' \
  -m 'Refs: #5 #9 #14 #47 #48'
```

Expected: one commit with 2 files.

---

### Task 3: Wire the artifact path into CI and gated workflows

**Files:**
- Modify: `.github/workflows/site-build.yml`
- Modify: `.github/workflows/deploy.yml`
- Modify: `.github/workflows/provenance.yml`
- Test: actionlint, zizmor, config_lint, check.py, audit_workflows, workflow hardening

- [ ] **Step 1: Patch site-build.yml**

Find this exact block in `.github/workflows/site-build.yml`:

```yaml
      - name: Build site
        run: just build-site
      - name: Install cosign
```

Replace with:

```yaml
      - name: Build site
        run: just build-site
      - name: Stage site artifact
        run: just stage-site
      - name: Install cosign
```

Do not change the following `Prepare artifact signature (non-blocking)` step: it keeps `continue-on-error: true` and its `if [ -d dist ]` guard.

- [ ] **Step 2: Patch deploy.yml**

Add pnpm/Node/install before the build, using the exact pins from `site-build.yml`. Find this exact block in `.github/workflows/deploy.yml`:

```yaml
      - name: Setup just
        uses: ./.github/actions/setup-just # zizmor: ignore[self-repository]
```

Replace with:

```yaml
      - name: Setup pnpm
        uses: pnpm/action-setup@73e46992e05b19abd31f2f3c20e0e7370d762115 # v6.1.1
      - name: Setup Node 22
        uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        with:
          node-version: '22.23.2'
          cache: pnpm
      - name: Install JS dependencies
        run: pnpm install --frozen-lockfile
      - name: Setup just
        uses: ./.github/actions/setup-just # zizmor: ignore[self-repository]
```

Then find this exact block in `.github/workflows/deploy.yml`:

```yaml
      - name: Build static artifact
        run: just build-site
      - name: Prepare hash and optional signature
        run: ./scripts/sign-artifact.sh dist
```

Replace with:

```yaml
      - name: Build static artifact
        run: just build-site
      - name: Stage static artifact
        run: just stage-site
      - name: Check site artifact
        run: just check-site-artifact
      - name: Prepare hash and optional signature
        run: ./scripts/sign-artifact.sh dist
```

Keep `vars.ENABLE_DEPLOY == 'true'`, `dry_run` guard and Environment unchanged. `just build-site` stays before `just stage-site`: `apps/site/dist` is gitignored and absent on a clean runner, so staging alone fails before the artifact check is reached.

- [ ] **Step 3: Patch provenance.yml**

Find this exact block in `.github/workflows/provenance.yml`:

```yaml
      - name: Build static artifact
        run: just build-site
      - name: Check artifact directory
        run: test -d dist
```

Replace with:

```yaml
      - name: Build static artifact
        run: just build-site
      - name: Stage static artifact
        run: just stage-site
      - name: Check site artifact
        run: just check-site-artifact
```

Keep guard `vars.ENABLE_PROVENANCE == 'true' && github.ref == 'refs/heads/main'`, permissions `contents: read`, `id-token: write`, `attestations: write`. `just build-site` stays before `just stage-site` for the same clean-runner reason.

- [ ] **Step 4: Verify workflow syntax and policy**

Run:

```bash
python3 scripts/config_lint.py
python3 scripts/check.py
python3 scripts/audit_workflows.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
uv run --with pyyaml==6.0.4 python scripts/check_runbook_commands.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN="$(gh auth token)" uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
git diff --check
```

Expected: config_lint JSON 24/TOML 4/workflow 22; `check.py` 201+ references; audit_workflows all external uses pinned; actionlint 0 errors; zizmor No findings.

- [ ] **Step 5: Commit**

Run:

```bash
git add .github/workflows/site-build.yml .github/workflows/deploy.yml .github/workflows/provenance.yml
git commit -m 'ci(devops): use staged site artifact in build and deploy' \
  -m 'Локальное изменение DevOps-цепочки. PR не создаётся, push не делается, ENABLE_* и алерты не включаются.' \
  -m 'site-build.yml теперь выполняет just stage-site после just build-site, поэтому существующий шаг подписи видит реальный корневой dist вместо честного skip. deploy.yml и provenance.yml используют тот же подготовленный артефакт и вызывают just check-site-artifact перед sign-artifact.sh.' \
  -m 'Контракт 404.html пока не полный: issue #5 открыта, поэтому чекер не добавлен в обязательный ci. В gated workflow он остаётся честной проверкой перед реальной выкладкой.' \
  -m 'Проверки: config_lint, check.py, audit_workflows, check_workflow_hardening, check_runbook_commands, actionlint 0 ошибок, zizmor No findings, git diff --check.' \
  -m 'Refs: #5 #9 #14 #47 #48'
```

Expected: one commit with 3 files.

---

### Task 4: Sync ops docs and run full verification

**Files:**
- Modify: `CONTRIBUTING.md`
- Modify: `docs/DEVOPS-STATUS.md`
- Modify: `docs/runbook.md`
- Test: full static suite and `just verify` with local PostgreSQL 18

- [ ] **Step 1: Patch CONTRIBUTING.md**

Use Python with exact replacements:

```python
from pathlib import Path

p = Path("CONTRIBUTING.md")
s = p.read_text(encoding="utf-8")

old = "`just check-env-contract`, `just check-ports`, `just check-image-pins` и `just check-ops-policy`."
new = "`just check-env-contract`, `just check-ports`, `just check-image-pins`, `just stage-site`, `just check-site-artifact` и `just check-ops-policy`."
assert s.count(old) == 1
s = s.replace(old, new, 1)

old = "Проверки сайта (`build-site`) подключаются по мере появления `apps/site`; сейчас это открытая зависимость PR #16. Те же проверки выполняются в CI, а итоговый обязательный статус называется `ci` — он будет зелёным только если все применимые проверки прошли."
new = "PR #16 влит, `apps/site` присутствует в `main`, поэтому `build-site` собирает Astro по-настоящему. Перед подписью и выкладкой используйте `just stage-site`: он копирует `apps/site/dist` в корневой `dist`. Контракт артефакта проверяет `just check-site-artifact`; до закрытия issue #5 он честно сообщает об отсутствии `404.html` и не ставится в обязательный `ci`. Итоговый обязательный статус называется `ci`."
assert s.count(old) == 1
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
```

- [ ] **Step 2: Patch docs/DEVOPS-STATUS.md**

Use Python with exact replacements:

```python
from pathlib import Path

p = Path("docs/DEVOPS-STATUS.md")
s = p.read_text(encoding="utf-8")

anchor = "| `check-alert-runbooks` | `just verify` (обязательно) | Каждое правило алерта ссылается на существующий якорь в runbook. |\n"
addition = (
    "| `stage-site` | Отдельно | Копирует `apps/site/dist` в корневой `dist`; саму сборку не меняет. |\n"
    "| `check-site-artifact` | Gated deploy/provenance, отдельно | Проверяет `dist/index.html` и `dist/404.html`; 404 ждёт issue #5. |\n"
)
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + addition, 1)

old = "| Отчёт `release-readiness` | Вердикт `NO-GO` — нормальное состояние до слияния PR #16 и адреса Q-1: нет артефакта, флагов и QA-адреса | После PR #16/Q-1 и появления артефакта `just release-readiness` пересчитает таблицу и покажет `READY` |"
new = "| Отчёт `release-readiness` | Вердикт `NO-GO` — нормальное состояние до адреса Q-1: нет флагов, QA-адреса и подготовленного артефакта | После Q-1 и появления артефакта `just release-readiness` пересчитает таблицу и покажет `READY` |"
assert s.count(old) == 1
s = s.replace(old, new, 1)

old = "- **PR #16** — минимальный Astro-сайт в `main`; без него `build-site` честно пропускается."
new = "- **PR #16** — минимальный Astro-сайт уже в `main`; `build-site` собирает его, а `stage-site` подготавливает корневой `dist`."
assert s.count(old) == 1
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
```

- [ ] **Step 3: Patch docs/runbook.md**

Use Python with exact replacements:

```python
from pathlib import Path

p = Path("docs/runbook.md")
s = p.read_text(encoding="utf-8")

old = """```bash
uvx --from rust-just just build-site
```

Команда проверяет контракт ADR 0014, валидирует материалы и медиа (`just check-content`) и собирает Astro, когда `apps/site` присутствует в main (PR #16). В CI те же шаги выполняются через `site-build` и итоговый статус `ci`."""
new = """```bash
uvx --from rust-just just build-site
uvx --from rust-just just stage-site
uvx --from rust-just just check-site-artifact
```

Команда проверяет контракт ADR 0014, валидирует материалы и медиа (`just check-content`) и собирает Astro, который теперь есть в `main` (PR #16). `stage-site` копирует `apps/site/dist` в корневой `dist`; `check-site-artifact` проверяет `index.html` и `404.html`. До закрытия issue #5 последний чекер сообщает об отсутствии страницы 404 — это зона фронтенда, а не DevOps. В CI те же шаги выполняются через `site-build`, итоговый статус `ci`."""
assert s.count(old) == 1
s = s.replace(old, new, 1)

old = """```bash
just build-site
scripts/deploy-static.sh deploy dist /srv/sreda/releases /srv/sreda/current
```"""
new = """```bash
just stage-site
just check-site-artifact
scripts/deploy-static.sh deploy dist /srv/sreda/releases /srv/sreda/current
```"""
assert s.count(old) == 1
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
```

- [ ] **Step 4: Full static verification**

Run:

```bash
set -euo pipefail
chmod +x scripts/stage-site.sh scripts/check_site_artifact.py
python3 -m py_compile scripts/check_site_artifact.py scripts/check.py scripts/config_lint.py
bash -n scripts/stage-site.sh scripts/sign-artifact.sh scripts/verify-artifact.sh scripts/deploy-static.sh
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
python3 scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN="$(gh auth token)" uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
SITE=/home/deb/.cache/mkdocs-site-artifact-plan
rm -rf "$SITE"
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir "$SITE" >/dev/null
rm -rf "$SITE"
python3 scripts/check_commit_messages.py
git diff --check
grep -nP '[\x{4e00}-\x{9fff}\x{3040}-\x{30ff}]' docs/superpowers CONTRIBUTING.md docs/DEVOPS-STATUS.md docs/runbook.md scripts/stage-site.sh scripts/check_site_artifact.py .github/workflows/site-build.yml .github/workflows/deploy.yml .github/workflows/provenance.yml || echo NO_FOREIGN
```

Expected: all checks exit 0, no CJK artefacts, `zizmor` No findings.

- [ ] **Step 5: Full just verify with PostgreSQL**

Run:

```bash
set -euo pipefail
uvx --from rust-just just api-db-up
trap 'uvx --from rust-just just api-db-down >/dev/null 2>&1 || true' EXIT
uvx --from rust-just just verify 2>&1 | tee /home/deb/just-verify-site-artifact.log | tail -30
```

Expected: final line `just verify: все проверки пройдены`. Real Astro build runs; `build-site` no longer skips. PostgreSQL container is stopped by trap.

- [ ] **Step 6: Final state check and commit**

Run:

```bash
git status --short
git log --oneline -8
gh pr list --repo Sreda-Media/sreda-media --state open --limit 10 --json number,title,state,headRefName
env | grep '^ENABLE_' || echo NO_ENABLE_VARS
grep -c 'enabled: "true"' deploy/observability/grafana-provisioning/alerting/rules.yml || true
```

Expected: only the three docs files unstaged before commit; no `ENABLE_*` variables; `enabled: "true"` count 0; no new PR created.

Commit:

```bash
git add CONTRIBUTING.md docs/DEVOPS-STATUS.md docs/runbook.md
git commit -m 'docs: reflect site artifact contract in ops docs' \
  -m 'Локальная синхронизация документации с новым контрактом артефакта. PR не создаётся, push не делается, гейты и алерты не включаются.' \
  -m 'CONTRIBUTING.md теперь описывает just stage-site и just check-site-artifact как отдельные read-only/подготовительные рецепты и фиксирует, что PR #16 уже влит. docs/DEVOPS-STATUS.md добавляет две строки в таблицу новых проверок, уточняет вердикт release-readiness и статус PR #16. docs/runbook.md использует stage-site/check-site-artifact в процедурах сборки и выкладки.' \
  -m 'Проверки: py_compile, bash -n, check.py, config_lint, check_links, check_runbook_commands, audit_workflows, workflow hardening, alert runbooks/rules, actionlint 0, zizmor No findings, mkdocs strict, check_commit_messages, diff --check, CJK-grep. Полный just verify с PostgreSQL 18 на 127.0.0.1:55432 зелёный.' \
  -m 'Refs: #5 #9 #14 #47 #48'
```

Expected: one commit with 3 files; working tree clean; local HEAD advanced; remote unchanged.

---

## Execution notes

- Do not create a new branch, PR, worktree or push. Work in the current `devops/chaos-self-heal` branch, already fast-forwarded to `origin/main`.
- Do not touch `apps/site/**`, PR #16, PR #50, `ci.yml`, `check_log_schema.py`, GitHub settings or alert enable flags.
- `404.html` is intentionally not created; issue #5 belongs to the frontend owner.
- All commits must keep detailed bodies and `Refs:`.
