# DevOps CI Hardening and Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить локальную проверку безопасности workflow, связать алерты с runbook и подготовить gated манифест релиза, не включая прод-гейты.

**Architecture:** Три независимых проверщика/скрипта в репозитории: read-only анализ `.github/workflows`, сверка `runbook_url` с якорями в документации и генерация `release.json` из артефакта. Всё интегрируется через `justfile`; новые проверки безопасности workflow и runbook-ссылок входят в `verify`, манифест остаётся вне `verify`/CI.

**Tech Stack:** Python 3 stdlib, PyYAML 6.0.4 через `uv run --with`, Bash, GitHub Actions YAML, MkDocs, `just`, `actionlint`, `zizmor`.

---

## Общий контекст для исполнителя

- Репозиторий: `/home/deb/Projects/Колледж/sreda-media`, ветка только `observability/foundation`.
- serv не трогать; новый PR не создавать; чужие PR/ветки, особенно PR #16, не трогать.
- Версия Ильи авторитетна: `check_log_schema.py`, `ci.yml`, `CONTRIBUTING.md`, базовый `justfile` из PR #45 не переписывать по существу.
- Коммиты только с подробными телами; текст целиком в коммите, не в PR.
- Секреты вне репозитория; в `.env.example` только имена переменных.
- Гейты `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE`, `SREDA_SITE_URL` не выставлять; правила алертов остаются `enabled: "false"`.
- Локально: Python 3.14.9, `caddy`/`just`/`gitleaks`/`cosign` не установлены, `systemd-analyze` и `gh` есть; actionlint `/tmp/opencode/bin/actionlint`; zizmor через `uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular`; mkdocs через `uvx --from mkdocs-material==9.8.2`.
- `just` запускать как `uvx --from rust-just just ...`.

### Task 1: Проверка безопасности workflow

**Files:**
- Create: `scripts/check_workflow_hardening.py`
- Modify: `justfile` — добавить `audit-hardening` после `audit-workflows` в `verify` и отдельный рецепт рядом с `audit-workflows`.
- Test: негативный прогон на временной копии `.github/workflows`.

- [ ] **Step 1: Записать проверщик целиком**

Создать `scripts/check_workflow_hardening.py` со следующим содержимым:

```python
#!/usr/bin/env python3
"""Проверка безопасности workflow: явные права и безопасные шаги."""
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
ELEVATED_TOP = {
    "auto-review.yml": {"pull-requests": "write"},
    "dependency-review.yml": {"pull-requests": "read"},
    "provenance.yml": {"id-token": "write", "attestations": "write"},
}
RUN_INJECTION = re.compile(
    r"\$\{\{\s*github(?:\.event|\[\s*['\"]event['\"]\s*\])(?:\.|\[)"
)
CHECKOUT_PREFIX = "actions/checkout@"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def iter_steps(data):
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        return
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield step


def check_file(path, errors):
    name = path.name
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"{name}: не удалось прочитать YAML: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(f"{name}: ожидается mapping")
        return

    perms = data.get("permissions")
    if perms is None:
        errors.append(f"{name}: нет top-level permissions")
    elif perms == "write-all":
        errors.append(f"{name}: permissions: write-all запрещены")
    elif not isinstance(perms, dict):
        errors.append(f"{name}: permissions должны быть mapping")
    else:
        if perms.get("contents") != "read":
            errors.append(f"{name}: permissions.contents должен быть read")
        allowed = {"contents": "read", **ELEVATED_TOP.get(name, {})}
        for scope, level in perms.items():
            if scope == "contents":
                continue
            if allowed.get(scope) != level:
                errors.append(f"{name}: неожиданные права {scope}: {level}")

    jobs = data.get("jobs") or {}
    if isinstance(jobs, dict):
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            job_perms = job.get("permissions")
            if job_perms is not None:
                expected = (
                    {"pages": "write", "id-token": "write"}
                    if name == "docs-pages.yml" and job_name == "deploy"
                    else {}
                )
                if job_perms != expected:
                    errors.append(
                        f"{name}: job {job_name} имеет неожиданные permissions: {job_perms}"
                    )

    events = data.get("on")
    if events is None:
        events = data.get(True)
    if isinstance(events, (dict, list)) and "pull_request_target" in events:
        errors.append(f"{name}: pull_request_target запрещён")
    is_pr = False
    if isinstance(events, dict):
        is_pr = "pull_request" in events
    elif isinstance(events, list):
        is_pr = "pull_request" in events

    for step in iter_steps(data):
        uses = step.get("uses")
        if is_pr and isinstance(uses, str) and uses.startswith(CHECKOUT_PREFIX):
            with_block = step.get("with") or {}
            if (
                not isinstance(with_block, dict)
                or str(with_block.get("persist-credentials")).lower() != "false"
            ):
                errors.append(f"{name}: checkout без persist-credentials: false")
        run = step.get("run")
        if isinstance(run, str) and RUN_INJECTION.search(run):
            errors.append(f"{name}: в run: используется github.event.*")


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    wf_dir = root / ".github/workflows"
    if not wf_dir.is_dir():
        fail_all([f"нет каталога workflow: {wf_dir}"])
    workflows = {
        p for pat in ("*.yml", "*.yaml") for p in wf_dir.glob(pat)
    }
    if not workflows:
        fail_all([f"нет workflow-файлов в {wf_dir}"])
    errors = []
    for path in sorted(workflows):
        check_file(path, errors)
    if errors:
        fail_all(errors)
    print("ok: workflow hardening — права, checkout и run: безопасны")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Добавить рецепт в `justfile`**

Найти блок:

```
# Ежедневная проверка относительных ссылок в docs/.
link-check:
    python3 scripts/check_links.py
```

Добавить сразу после него:

```
# Политика безопасности workflow: права, checkout и run:.
audit-hardening:
    uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
```

В строке `verify:` заменить `... config-lint workflows-lint secrets ...` на `... config-lint workflows-lint audit-hardening secrets ...`.

- [ ] **Step 3: Прогнать позитив и негатив**

```bash
chmod +x scripts/check_workflow_hardening.py
python3 -m py_compile scripts/check_workflow_hardening.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
```

Ожидаемый вывод: `ok: workflow hardening — права, checkout и run: безопасны`.

Негатив:

```bash
TMP=$(mktemp -d)
cp -a .github "$TMP/.github"
python3 - "$TMP" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1]) / ".github/workflows/alert-drill.yml"
s = p.read_text(encoding="utf-8")
s = s.replace("permissions:\n  contents: read", "permissions: write-all", 1)
s = s.replace("run: just alert-drill", 'run: echo "${{ github.event.head_commit.message }}"', 1)
p.write_text(s, encoding="utf-8")
PY
if uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py "$TMP"; then
  echo "ОШИБКА: негативный тест не упал"
  rm -rf "$TMP"
  exit 1
fi
rm -rf "$TMP"
```

Ожидаемо несколько строк `FAIL:` и exit 1.

- [ ] **Step 4: Обычные проверки и коммит**

```bash
python3 scripts/check.py
python3 scripts/config_lint.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
uvx --from rust-just just --list >/dev/null
git add scripts/check_workflow_hardening.py justfile
git commit -F- <<'MSG'
feat(devops): add workflow hardening guard

Добавлена локальная проверка политики безопасности workflow. serv, PR #16 и
чужие ветки не трогались; новый PR не создавался; гейты не включались.

Что сделано:
- scripts/check_workflow_hardening.py читает все .github/workflows/*.yml через
  PyYAML и требует явные permissions без write-all, contents: read и список
  разрешённых исключений: pull-requests: write только в auto-review.yml,
  pull-requests: read только в dependency-review.yml, id-token/attestations
  только в provenance.yml, job-level pages/id-token только в job deploy файла
  docs-pages.yml;
- запрещены pull_request_target, checkout без persist-credentials: false на
  PR-событиях и подстановки github.event.* внутри run:;
- проверщик поддерживает опциональный корень репозитория для негативных тестов;
- рецепт audit-hardening добавлен в just verify после audit-workflows.

Проверки: py_compile, позитив ok, негатив с write-all и github.event.* в run:
падает с exit 1, check.py, config_lint, actionlint 0 ошибок, zizmor No findings,
just --list валиден.

Refs: #9 #26
MSG
```

### Task 2: Runbook-ссылки у алертов, шаблон инцидента и ротация age-ключа

**Files:**
- Modify: `deploy/observability/grafana-provisioning/alerting/rules.yml`
- Modify: `docs/runbook.md`
- Modify: `deploy/observability/.env.example`
- Modify: `docs/SECRET-ROTATION.md`
- Modify: `justfile`
- Create: `scripts/check_alert_runbooks.py`
- Create: `docs/incidents/template.md`
- Create: `docs/BACKUP-KEY-ROTATION.md`
- Modify: `mkdocs.yml` — добавить две страницы в раздел «Эксплуатация».

- [ ] **Step 1: Добавить runbook_url во все правила**

Выполнить:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("deploy/observability/grafana-provisioning/alerting/rules.yml")
text = p.read_text(encoding="utf-8")
uids = [
    "sreda-log-errors",
    "sreda-health-probe-failed",
    "sreda-rollback-finished",
    "sreda-grafana-errors",
    "sreda-loki-errors",
    "sreda-backup-failed",
    "sreda-disk-low",
    "sreda-slo-fast-burn",
    "sreda-slo-slow-burn",
    "sreda-backup-stale",
]
needle = "        annotations:\n"
for uid in uids:
    start = text.index(f"      - uid: {uid}\n")
    pos = text.index(needle, start) + len(needle)
    url = f"          runbook_url: https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#{uid}\n"
    text = text[:pos] + url + text[pos:]
p.write_text(text, encoding="utf-8")
PY
python3 -c 'import yaml; d=yaml.safe_load(open("deploy/observability/grafana-provisioning/alerting/rules.yml")); print(sum(len(g["rules"]) for g in d["groups"]))'
```

Ожидаемый вывод: `10`.

- [ ] **Step 2: Добавить якоря в `docs/runbook.md`**

Сразу после строк:

```
Документ для дежурного. Актуальная версия: этап 0.1 (статическая витрина).
Основание: ADR 0006 (VPS + Caddy), ADR 0015 (Runtime and Data Operations), issues #7, #9, #14.
```

вставить:

```
## Быстрые ссылки по алертам

Каждое правило Grafana Alerting ссылается на соответствующий якорь ниже. Правила остаются отключёнными до PR #16 и Q-1; включение — отдельное изменение с обновлением проверяющих скриптов.

<a id="sreda-log-errors"></a>
<a id="sreda-health-probe-failed"></a>
<a id="sreda-rollback-finished"></a>
<a id="sreda-grafana-errors"></a>
<a id="sreda-loki-errors"></a>
<a id="sreda-backup-failed"></a>
<a id="sreda-disk-low"></a>
<a id="sreda-slo-fast-burn"></a>
<a id="sreda-slo-slow-burn"></a>
<a id="sreda-backup-stale"></a>
```

- [ ] **Step 3: Написать проверщик**

Создать `scripts/check_alert_runbooks.py`:

```python
#!/usr/bin/env python3
"""Сверка runbook_url правил Grafana Alerting с якорями в docs/runbook.md."""
import json
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"
SLO = ROOT / "deploy/observability/slo.json"
RUNBOOK = ROOT / "docs/runbook.md"
PREFIX = "https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}")
    raise SystemExit(1)


def main():
    errors = []
    try:
        slo = json.loads(SLO.read_text(encoding="utf-8"))
        expected = set(slo["rule_uids"])
        data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
        runbook = RUNBOOK.read_text(encoding="utf-8")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        fail_all([f"не удалось прочитать входные файлы: {exc}"])

    seen = set()
    for group in data.get("groups") or []:
        for rule in group.get("rules") or []:
            uid = rule.get("uid")
            if not uid:
                errors.append("правило без uid")
                continue
            seen.add(uid)
            annotations = rule.get("annotations") or {}
            wanted = f"{PREFIX}{uid}"
            if annotations.get("runbook_url") != wanted:
                errors.append(f"{uid}: runbook_url должен быть {wanted}")
            if f'<a id="{uid}"></a>' not in runbook:
                errors.append(f'{uid}: в docs/runbook.md нет якоря <a id="{uid}"></a>')

    missing = expected - seen
    if missing:
        errors.append("в rules.yml нет UID из slo.json: " + ", ".join(sorted(missing)))
    if errors:
        fail_all(errors)
    print(f"ok: alert runbooks — {len(seen)} правил со ссылками и якорями")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Подключить проверку к `justfile`**

Добавить после рецепта `check-alerts`:

```
# Runbook-ссылки алертов: у каждого правила есть якорь в docs/runbook.md.
check-alert-runbooks:
    uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
```

В строке `verify:` заменить `check check-logs check-alerts check-uptime` на `check check-logs check-alerts check-alert-runbooks check-uptime`.

- [ ] **Step 5: Создать docs и env-шаблон**

Создать `docs/incidents/template.md`:

```
# Инцидент: <краткое название>

- **Начало (UTC):**
- **Окончание (UTC):**
- **Владелец:**
- **Затронутый сервис:**
- **Уровень:** informative / warning / critical

## Влияние

Что именно было недоступно или работало некорректно, сколько пользователей затронуто.

## Хронология

- HH:MM — что произошло, кто заметил.
- HH:MM — какие действия выполнены.

## Корень проблемы

Фактическая причина, подтверждённая логами/метриками. Если причина не найдена — явно написать «не установлено».

## Разрешение

Какие действия восстановили сервис; ссылка на релиз или откат.

## Action items

- [ ] Действие — владелец — срок.

## Ссылки

- Правило алерта: `<uid>`.
- Runbook: `docs/runbook.md`.
```

Создать `docs/BACKUP-KEY-ROTATION.md`:

```
# Ротация ключа шифрования бэкапов

Операционные бэкапы шифруются через `age`, если на VPS задан
`SREDA_BACKUP_AGE_RECIPIENT`. При восстановлении используется
`SREDA_BACKUP_AGE_IDENTITY`. Значения хранятся вне репозитория; здесь
описан только порядок ротации.

## Порядок

1. Сгенерировать новую пару `age` на VPS или в защищённом хранилище.
2. Записать новый **публичный** получатель в `SREDA_BACKUP_AGE_RECIPIENT`.
3. Записать новый **приватный** identity в защищённое хранилище и задать
   `SREDA_BACKUP_AGE_IDENTITY` только при восстановлении.
4. Сделать новый бэкап: `just backup-obs`; убедиться, что появились `.age`-файлы
   и манифест SHA256.
5. Проверить восстановление в безопасном контуре: `just backup-drill` и
   `just restore-obs <UTC-префикс>` с `CONFIRM=1` только на тестовом каталоге.
6. Не удалять старый identity, пока не истечёт `RETENTION_DAYS` и не будет
   подтверждено восстановление всех актуальных копий.
7. Отозвать старый ключ и зафиксировать дату ротации в журнале ниже.

## Проверки

`just secrets` ищет утечки в git, но не проверяет срок жизни ключа. Факт ротации
фиксируется вручную.

## История ротации

- Записи добавлять вручную: дата, тип ключа, владелец. Без самих значений.
```

В `deploy/observability/.env.example` добавить в конец:

```
# Шифрование бэкапов: только имена переменных, значения задаются на VPS.
# SREDA_BACKUP_AGE_RECIPIENT=<публичный получатель age>
# SREDA_BACKUP_AGE_IDENTITY=<путь к приватному identity age>
```

В `docs/SECRET-ROTATION.md` после раздела «Что ротировать» добавить строку:

```
- Ключ шифрования бэкапов: см. `docs/BACKUP-KEY-ROTATION.md`.
```

В `mkdocs.yml` в раздел «Эксплуатация» после `- Runbook: runbook.md` добавить:

```
      - Шаблон инцидента: incidents/template.md
      - Ротация ключа бэкапов: BACKUP-KEY-ROTATION.md
```

- [ ] **Step 6: Проверить позитив и негатив**

```bash
chmod +x scripts/check_alert_runbooks.py
python3 -m py_compile scripts/check_alert_runbooks.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
python3 scripts/check_slo.py
```

Позитив: `ok: alert runbooks — 10 правил со ссылками и якорями`, `10 правил`, `ok` от `check_slo`.

Негатив с восстановлением:

```bash
cp deploy/observability/grafana-provisioning/alerting/rules.yml /tmp/opencode/rules-backup.yml
python3 - <<'PY'
from pathlib import Path
p = Path("deploy/observability/grafana-provisioning/alerting/rules.yml")
s = p.read_text(encoding="utf-8")
s = s.replace("          runbook_url: https://github.com/Sreda-Media/sreda-media/blob/main/docs/runbook.md#sreda-log-errors\n", "", 1)
p.write_text(s, encoding="utf-8")
PY
if uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py; then
  cp /tmp/opencode/rules-backup.yml deploy/observability/grafana-provisioning/alerting/rules.yml
  echo "ОШИБКА: негативный тест не упал"
  exit 1
fi
cp /tmp/opencode/rules-backup.yml deploy/observability/grafana-provisioning/alerting/rules.yml
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
grep -c 'enabled: "true"' deploy/observability/grafana-provisioning/alerting/rules.yml || true
python3 scripts/check.py
python3 scripts/config_lint.py
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-alert-runbooks
```

Последний `grep` должен вывести `0` или не найти совпадений.

- [ ] **Step 7: Коммит**

```bash
git add deploy/observability/grafana-provisioning/alerting/rules.yml docs/runbook.md docs/incidents/template.md docs/BACKUP-KEY-ROTATION.md docs/SECRET-ROTATION.md deploy/observability/.env.example scripts/check_alert_runbooks.py justfile mkdocs.yml
git commit -F- <<'MSG'
docs(devops): link alerts to runbooks and add ops templates

Операционная готовность без включения алертов и без захода на serv. PR #16 и
чужие ветки не трогались, новый PR не создавался, гейты не включались.

Что сделано:
- все 10 правил в deploy/observability/grafana-provisioning/alerting/rules.yml
  получили annotations.runbook_url на docs/runbook.md с якорем по uid;
- в docs/runbook.md добавлены явные HTML-якоря для всех uid, поэтому ссылки
  стабильны при изменении заголовков;
- scripts/check_alert_runbooks.py и рецепт check-alert-runbooks в verify
  сверяют runbook_url, якоря и наличие всех rule_uids из slo.json;
- docs/incidents/template.md — шаблон разбора инцидента;
- docs/BACKUP-KEY-ROTATION.md — порядок ротации SREDA_BACKUP_AGE_RECIPIENT
  и SREDA_BACKUP_AGE_IDENTITY; в .env.example только имена переменных;
- docs/SECRET-ROTATION.md ссылается на новую памятку; обе страницы добавлены
  в навигацию MkDocs.

Проверки: py_compile, check_alert_runbooks ok на 10 правилах, негатив с
удалённым runbook_url падает и восстанавливается, check_alert_rules,
check_slo, check.py, config_lint, mkdocs build --strict, grep enabled=true — 0.
Правила остались enabled=false.

Refs: #9 #14
MSG
```

### Task 3: Gated манифест релиза

**Files:**
- Create: `scripts/release-manifest.sh`
- Modify: `justfile` — рецепт `release-manifest path` вне `verify`.

- [ ] **Step 1: Написать скрипт**

Создать `scripts/release-manifest.sh`:

```bash
#!/usr/bin/env bash
# Манифест собранного артефакта: хэш, git-состояние и статус гейтов.
# Не подписывает, не выкладывает и не включает флаги. Использование:
#   scripts/release-manifest.sh dist/
set -euo pipefail

ARTIFACT="${1:-dist}"
fail() { printf '[release-manifest] ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ -d "$ARTIFACT" ] || fail "нет каталога артефакта: $ARTIFACT"
[ -f "$ARTIFACT/artifact.sha256" ] || fail "нет artifact.sha256 в $ARTIFACT"

SHA256="$(awk 'NR==1 {print $1}' "$ARTIFACT/artifact.sha256")"
[ -n "$SHA256" ] || fail "artifact.sha256 пуст"
GIT_SHA="$(git rev-parse HEAD)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COSIGN_VERIFIED=false
if [ -f "$ARTIFACT/cosign.sig" ] && [ -f "$ARTIFACT/cosign.pem" ] && command -v cosign >/dev/null 2>&1; then
    COSIGN_VERIFIED=true
fi

python3 - "$ARTIFACT/release.json" "$SHA256" "$GIT_SHA" "$GIT_BRANCH" "$COSIGN_VERIFIED" <<'PY'
import datetime
import json
import os
import sys

out, sha256, git_sha, git_branch, cosign = sys.argv[1:6]
manifest = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "git_sha": git_sha,
    "git_branch": git_branch,
    "artifact_sha256": sha256,
    "cosign_verified": cosign == "true",
    "gates": {
        "ENABLE_DEPLOY": os.getenv("ENABLE_DEPLOY", "") == "true",
        "ENABLE_DOCS_PAGES": os.getenv("ENABLE_DOCS_PAGES", "") == "true",
        "ENABLE_PROVENANCE": os.getenv("ENABLE_PROVENANCE", "") == "true",
        "SREDA_SITE_URL": bool(os.getenv("SREDA_SITE_URL", "")),
    },
    "operator": os.getenv("USER", "unknown"),
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY

printf '[release-manifest] подготовлен %s/release.json (гейты не включались)\n' "$ARTIFACT"
```

- [ ] **Step 2: Добавить рецепт**

После рецепта `verify-artifact path` добавить:

```
# Манифест релиза как код; не входит в verify и CI.
release-manifest path:
    bash scripts/release-manifest.sh "{{path}}"
```

- [ ] **Step 3: Проверить на temp-артефакте**

```bash
chmod +x scripts/release-manifest.sh
bash -n scripts/release-manifest.sh
ART=/tmp/opencode/release-manifest-check
rm -rf "$ART" && mkdir -p "$ART"
printf '<html>Sreda Media</html>\n' > "$ART/index.html"
printf '<html>404</html>\n' > "$ART/404.html"
printf '<html>Sreda Media</html>\n' > "$ART/artifact.tar.gz"
( cd "$ART" && sha256sum artifact.tar.gz > artifact.sha256 )
./scripts/release-manifest.sh "$ART"
python3 -m json.tool "$ART/release.json"
python3 - "$ART/release.json" <<'PY'
import json, subprocess, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
assert m["git_sha"] == head
assert m["cosign_verified"] is False
assert not any(m["gates"].values())
print("ok: manifest matches HEAD and gates are off")
PY
python3 scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
python3 scripts/check.py
```

Ожидаемый вывод: валидный JSON и `ok: manifest matches HEAD and gates are off`.

- [ ] **Step 4: Коммит**

```bash
git add scripts/release-manifest.sh justfile
git commit -F- <<'MSG'
chore(devops): add gated release manifest

Манифест релиза подготовлен как код, но не включён в verify/CI и не меняет
гейты. serv, PR #16 и чужие ветки не трогались, новый PR не создавался.

Что сделано:
- scripts/release-manifest.sh принимает каталог артефакта и пишет release.json
  с UTC-временем, git SHA и веткой, artifact_sha256 из artifact.sha256,
  статусом cosign и состояниями ENABLE_DEPLOY/ENABLE_DOCS_PAGES/
  ENABLE_PROVENANCE/SREDA_SITE_URL;
- отсутствие cosign честно даёт cosign_verified: false, а не ошибку;
- скрипт не подписывает, не выкладывает и не меняет артефакт;
- рецепт just release-manifest path добавлен вне verify и CI.

Проверки: bash -n, генерация на temp-артефакте, json.tool, сверка git_sha
с HEAD, все гейты false, check_runbook_commands, audit_workflows, check.py.

Refs: #9 #14
MSG
```

### Task 4: Финальная синхронизация документации и верификация

**Files:**
- Modify: `CONTRIBUTING.md`
- Modify: `docs/DEVOPS-STATUS.md`
- Modify: `mkdocs.yml` — только если нужно поправить метки навигации после Task 2.

- [ ] **Step 1: Обновить `CONTRIBUTING.md`**

В абзаце про `verify` после перечисления `just check-uptime`, `just docs-build` и `just link-check` добавить `just audit-hardening` и `just check-alert-runbooks`. В списке неблокирующих рецептов после `just sign-artifact dist` добавить `just release-manifest dist` с пометкой, что манифест не подписывает и не выкладывает.

- [ ] **Step 2: Обновить `docs/DEVOPS-STATUS.md`**

В таблицу «Новые проверки готового контура» добавить строки:

```
| `audit-hardening` | `just verify` | Да | Права workflow, persist-credentials, отсутствие github.event.* в run:. |
| `check-alert-runbooks` | `just verify` | Да | Каждое правило алерта ссылается на существующий якорь в runbook. |
| `release-manifest` | `workflow_dispatch` / вручную | Нет | Манифест артефакта как код, без подписи и выкладки. |
```

В раздел «Подготовлено, но не включено» добавить:

```
| Манифест релиза | Готов как рецепт, но не входит в CI | `just release-manifest dist` после появления артефакта |
```

Раздел «Идеи на потом» оставить без изменений: пункта про связь алертов и runbook там нет. Добавить в «Ссылки» строки на `docs/incidents/template.md` и `docs/BACKUP-KEY-ROTATION.md`.

- [ ] **Step 3: Полная статическая верификация**

```bash
chmod +x scripts/check_workflow_hardening.py scripts/check_alert_runbooks.py scripts/release-manifest.sh
python3 -m py_compile scripts/check_workflow_hardening.py scripts/check_alert_runbooks.py
bash -n scripts/release-manifest.sh
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_log_schema.py
python3 scripts/check_uptime_config.py
python3 scripts/check_links.py
python3 scripts/check_host_config.py
uv run --with pyyaml==6.0.4 python scripts/check_slo.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
python3 scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-ci-final
grep -nP '[\x{4e00}-\x{9fff}\x{3040}-\x{30ff}]' CONTRIBUTING.md docs/DEVOPS-STATUS.md docs/incidents/template.md docs/BACKUP-KEY-ROTATION.md scripts/*.py scripts/*.sh || true
```

Ожидаемо: все проверки зелёные, actionlint 0, zizmor No findings, grep пустой.

- [ ] **Step 4: Полный `just verify` с PostgreSQL**

```bash
uvx --from rust-just just api-db-up
trap 'uvx --from rust-just just api-db-down >/dev/null 2>&1 || true' EXIT
uvx --from rust-just just verify 2>&1 | tee /tmp/opencode/just-verify-ci-hardening.log | tail -25
```

Ожидаемый финал лога: `just verify: все проверки пройдены`. build-site пропускается из-за PR #16.

- [ ] **Step 5: Коммит и push**

```bash
git add CONTRIBUTING.md docs/DEVOPS-STATUS.md mkdocs.yml
git commit -F- <<'MSG'
docs: reflect workflow and ops hardening checks

Финальная синхронизация документации после трёх новых DevOps-задач. serv,
PR #16 и чужие ветки не трогались, новый PR не создавался, гейты не включались.

Что сделано:
- CONTRIBUTING.md: audit-hardening и check-alert-runbooks перечислены в verify,
  release-manifest — в списке неблокирующих рецептов;
- docs/DEVOPS-STATUS.md: три новые строки в карте проверок, строка в таблице
  «Подготовлено, но не включено», ссылки на шаблон инцидента и ротацию
  age-ключа;
- навигация MkDocs осталась согласованной с новыми страницами.

Проверки: py_compile, bash -n, check.py, config_lint, check_log_schema,
check_uptime_config, check_links, check_host_config, check_slo,
check_alert_rules, check_alert_runbooks, check_workflow_hardening,
check_runbook_commands, audit_workflows, actionlint 0 ошибок, zizmor
No findings, mkdocs build --strict, полный just verify с PostgreSQL 18
на 127.0.0.1:55432 (лог /tmp/opencode/just-verify-ci-hardening.log).

Refs: #9 #14 #26 #35
MSG
git push origin observability/foundation
```

- [ ] **Step 6: Финальная сверка**

```bash
git status --short
git log --oneline -7
git ls-remote --heads origin observability/foundation
grep -c 'enabled: "true"' deploy/observability/grafana-provisioning/alerting/rules.yml || true
```

Ожидаемо: дерево чистое, remote head совпадает с локальным, `grep` даёт `0` или пусто.
