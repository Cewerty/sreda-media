# DevOps readiness and hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Свести готовность к выкладке, гигиену конфигурации, операционную политику и мета-линт процесса к пятью небольшим read-only проверкам без включения каких-либо прод-флагов.

**Architecture:** Каждый модуль — источник правды в репозитории (или read-only `gh`) → проверяющий Python-скрипт с необязательным `argv[1]` как корнем репозитория → табличный stdout → рецепт `just`. Гигиена и политика входят в `verify`; readiness и мета-линт запускаются вручную. `NO-GO` и `SKIP` — нормальные вердикты с `exit 0`; `exit 1` только на реальную ошибку ввода или нарушение контракта.

**Tech Stack:** Python 3.14 stdlib, PyYAML 6.0.4 через `uv run --with`, `just`, `git`, `gh`, MkDocs, GitHub Actions lint tools.

---

### Task 1: Go/No-Go readiness как код

**Files:**
- Create: `scripts/release_readiness.py`
- Modify: `justfile` — рецепт `release-readiness` после `release-manifest`, НЕ в `verify`

- [ ] **Step 1: Записать скрипт**

Создать `scripts/release_readiness.py` ровно с этим содержимым:

```python
#!/usr/bin/env python3
"""Read-only отчёт о готовности к выкладке (issues #9, #14)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
REPO = "Sreda-Media/sreda-media"
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"
FLAGS = ("ENABLE_DEPLOY", "ENABLE_DOCS_PAGES", "ENABLE_PROVENANCE", "SREDA_SITE_URL")
DOCS = (
    "docs/DEVOPS-STATUS.md",
    "docs/runbook.md",
    "docs/slo.md",
    "docs/resource-budget.md",
)
ARTIFACT_FILES = ("index.html", "404.html", "artifact.tar.gz", "artifact.sha256")


def fail(message):
    raise SystemExit(f"FAIL: {message}")


def run(cmd):
    try:
        return subprocess.run(
            cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=30
        ), None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)


def git_out(args):
    proc, err = run(["git", *args])
    if proc is None or proc.returncode != 0:
        return None
    return proc.stdout.strip()


def add(rows, name, state, comment):
    rows.append((name, state, comment))


def git_row(rows):
    head = git_out(["rev-parse", "--short", "HEAD"])
    branch = git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    status = git_out(["status", "--porcelain"])
    if head is None or branch is None or status is None:
        add(rows, "git", "SKIP", "git недоступен")
    elif status:
        add(rows, "git", "NO", f"{branch}@{head}, рабочее дерево не чистое")
    else:
        add(rows, "git", "OK", f"{branch}@{head}, дерево чистое")


def artifact_row(rows):
    directory = ROOT / "dist"
    missing = [name for name in ARTIFACT_FILES if not (directory / name).is_file()]
    if missing:
        add(rows, "артефакт", "NO", "нет: " + ", ".join(missing))
        return
    signed = (directory / "cosign.sig").is_file() and (directory / "cosign.pem").is_file()
    add(rows, "артефакт", "OK", "index/404/tar/sha256 на месте; подпись: " + ("есть" if signed else "нет"))


def flags_row(rows, values):
    unset = [name for name in FLAGS if not values.get(name)]
    if unset:
        add(rows, "флаги", "NO", "не заданы: " + ", ".join(unset))
    else:
        add(rows, "флаги", "OK", "ENABLE_* и SREDA_SITE_URL заданы")


def alerts_row(rows):
    try:
        data = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        fail(f"rules.yml: не удалось прочитать YAML: {exc}")
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        fail("rules.yml: нет groups")
    rules = []
    for group in groups:
        if isinstance(group, dict) and isinstance(group.get("rules"), list):
            rules.extend(rule for rule in group["rules"] if isinstance(rule, dict))
    enabled = []
    for rule in rules:
        labels = rule.get("labels")
        level = labels.get("enabled", "false") if isinstance(labels, dict) else "false"
        if str(level).lower() == "true":
            enabled.append(str(rule.get("uid", "без uid")))
    if enabled:
        add(rows, "алерты", "NO", "включены: " + ", ".join(enabled))
    else:
        add(rows, "алерты", "OK", f"{len(rules)} правил, все выключены")


def pr_row(rows):
    proc, err = run([
        "gh", "pr", "view", "16", "--repo", REPO, "--json", "state,mergeable"
    ])
    if proc is None or proc.returncode != 0:
        detail = err or (proc.stderr.strip().splitlines() or ["gh недоступен"])[0]
        add(rows, "PR #16", "SKIP", detail)
        return
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        add(rows, "PR #16", "SKIP", "не удалось разобрать ответ gh")
        return
    state = str(data.get("state", ""))
    mergeable = str(data.get("mergeable", ""))
    if state.upper() == "MERGED":
        add(rows, "PR #16", "OK", f"state={state}, mergeable={mergeable}")
    else:
        add(rows, "PR #16", "NO", f"state={state}, mergeable={mergeable}")


def docs_row(rows):
    missing = [rel for rel in DOCS if not (ROOT / rel).is_file()]
    if missing:
        fail("нет обязательного документа: " + ", ".join(missing))
    add(rows, "доки", "OK", f"{len(DOCS)} документов на месте")


def qa_row(rows, site_url):
    if not site_url:
        add(rows, "QA-адрес", "NO", "SREDA_SITE_URL не задан")
        return
    checks = (
        ("deploy/uptime-kuma/monitors.json", "${SREDA_SITE_URL}"),
        ("deploy/observability/prometheus-external.yml.template", "${SREDA_SITE_URL}"),
        ("deploy/host/Caddyfile.template", "{{SREDA_SITE_URL}}"),
    )
    problems = []
    for rel, token in checks:
        path = ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            fail(f"{rel}: не удалось прочитать: {exc}")
        if token not in text or "sreda.sielom.ru" in text:
            problems.append(rel)
    if problems:
        add(rows, "QA-адрес", "NO", "адрес захардкожен: " + ", ".join(problems))
    else:
        add(rows, "QA-адрес", "OK", "адрес только через переменную или плейсхолдер")


def main():
    values = {name: os.environ.get(name, "") for name in FLAGS}
    rows = []
    git_row(rows)
    artifact_row(rows)
    flags_row(rows, values)
    alerts_row(rows)
    pr_row(rows)
    docs_row(rows)
    qa_row(rows, values["SREDA_SITE_URL"])

    print(f"{'Проверка':22} | {'Состояние':9} | Комментарий")
    print("-" * 78)
    for name, state, comment in rows:
        print(f"{name:22} | {state:9} | {comment}")
    verdict = "READY" if all(state == "OK" for _, state, _ in rows) else "NO-GO"
    print(f"ИТОГ: {verdict}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Добавить рецепт**

В `justfile` после рецепта `release-manifest path` добавить:

```just
# Read-only отчёт о готовности к выкладке; ничего не включает и не публикует.
release-readiness:
    uv run --with pyyaml==6.0.4 python scripts/release_readiness.py
```

`verify` НЕ трогать.

- [ ] **Step 3: Позитивный прогон**

```bash
chmod +x scripts/release_readiness.py
python3 -m py_compile scripts/release_readiness.py
uv run --with pyyaml==6.0.4 python scripts/release_readiness.py
```

Expected: таблица из 7 строк, `ИТОГ: NO-GO` (нет артефакта, флагов и PR #16 ещё в main), `exit 0`.

- [ ] **Step 4: Негативный прогон**

```bash
TMP=$(mktemp -d)
cp -a deploy docs "$TMP"/
mkdir -p "$TMP/dist"
printf 'x' > "$TMP/dist/artifact.tar.gz"
printf '%s  %s\n' "$(printf x | sha256sum | cut -d' ' -f1)" artifact.tar.gz > "$TMP/dist/artifact.sha256"
printf 'groups: []\n' > "$TMP/deploy/observability/grafana-provisioning/alerting/rules.yml"
uv run --with pyyaml==6.0.4 python scripts/release_readiness.py "$TMP"
echo "rc=$?"
rm -rf "$TMP"
```

Expected: последняя строка `rc=1`, в выводе `FAIL: rules.yml: нет groups`. Артефакт без `index.html`/`404.html` даёт строку `NO`, но не падает.

- [ ] **Step 5: Коммит**

```bash
git add scripts/release_readiness.py justfile
git commit -F- <<'MSG'
chore(devops): add release readiness report

Добавлен read-only отчёт о готовности к выкладке в observability/foundation.
Новый PR не создавался, serv и чужие ветки не трогались, гейты не включались.

- scripts/release_readiness.py собирает таблицу git/артефакт/флаги/алерты/
  PR #16/доки/QA-адрес и печатает ИТОГ READY или NO-GO.
- Пустые флаги, отсутствующий артефакт и незакрытый PR #16 — нормальный
  NO-GO с exit 0; недоступный gh — SKIP в строке PR #16.
- exit 1 только на реальную ошибку ввода (битый rules.yml, отсутствующий
  обязательный документ, нечитаемый файл адреса).
- Рецепт release-readiness добавлен в justfile после release-manifest и НЕ
  входит в verify или CI.

Проверки: py_compile, позитивный прогон (NO-GO, exit 0), негатив с пустыми
groups (FAIL, exit 1), check.py, config_lint.py.

Refs: #9 #14
MSG
```

---

### Task 2: Гигиена конфигурации в verify

**Files:**
- Create: `scripts/check_env_contract.py`
- Create: `scripts/check_ports.py`
- Create: `scripts/check_image_pins.py`
- Modify: `justfile` — три рецепта и три имени в `verify` после `config-lint`

- [ ] **Step 1: Проверка контракта env**

Создать `scripts/check_env_contract.py`:

```python
#!/usr/bin/env python3
"""Read-only сверка плейсхолдеров ${VAR} с шаблонами окружения."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".ruff_cache", ".venv"}
PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
ASSIGN = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.M)
TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")
SHELL_LOCAL = {
    "PREFIX", "RETENTION_DAYS", "TS", "SQL_FILE", "GRAFANA_FILE", "SREDA_SITE_URL",
}
SCAN_DIRS = ("deploy", ".github", "scripts")
SCAN_FILES = ("justfile",)
ENV_FILES = ("deploy/observability/.env.example", "apps/cms-api/.env.example")


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def read(rel):
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail_all([f"{rel}: не удалось прочитать: {exc}"])


def known_names():
    names = set()
    for rel in ENV_FILES:
        names.update(ASSIGN.findall(read(rel)))
    names.update(TOKEN.findall(read("docs/SECRET-ROTATION.md")))
    names.update(SHELL_LOCAL)
    return names


def source_files():
    found = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            fail_all([f"нет каталога: {rel}"])
        for path in base.rglob("*"):
            if path.is_file() and not SKIP_DIRS.intersection(path.parts):
                if path.suffix != ".pyc":
                    found.append(path)
    for rel in SCAN_FILES:
        path = ROOT / rel
        if path.is_file():
            found.append(path)
    return found


def main():
    known = known_names()
    found = {}
    for path in source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for name in PLACEHOLDER.findall(text):
            found.setdefault(name, str(path.relative_to(ROOT)))
    unknown = sorted(set(found) - known)
    if unknown:
        fail_all([f"${{{name}}}: нет в .env.example или документации ({found[name]})" for name in unknown])
    print(f"ok: env contract — {len(found)} плейсхолдеров, все объявлены")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Проверка карты портов**

Создать `scripts/check_ports.py`:

```python
#!/usr/bin/env python3
"""Read-only проверка карты портов compose-файлов (ADR 0006)."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
BIND = re.compile(r'^\s*-\s*"(?:([^:]+):)?(\d+):(\d+)"\s*$')
EXPECTED = {
    "dev/postgres.yml": {55432},
    "dev/docker-compose.yml": {13000, 13100, 13345},
    "observability/docker-compose.yml": {3000, 3100, 12345, 9090, 9100, 9115, 5432, 8000},
    "uptime-kuma/docker-compose.yml": {3001},
}


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def main():
    errors = []
    seen = set()
    for rel, expected in EXPECTED.items():
        path = ROOT / "deploy" / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{rel}: не удалось прочитать: {exc}")
            continue
        ports = []
        for line in text.splitlines():
            match = BIND.match(line)
            if not match:
                continue
            host, published, container = match.groups()
            if host != "127.0.0.1":
                errors.append(f"{rel}: порт {published} не привязан к 127.0.0.1")
            port = int(published)
            ports.append(port)
        if len(ports) != len(set(ports)):
            errors.append(f"{rel}: дублирование host-портов")
        actual = set(ports)
        if actual != expected:
            errors.append(
                f"{rel}: ожидаемые порты {sorted(expected)}, фактические {sorted(actual)}"
            )
        seen.update(actual)
    if errors:
        fail_all(errors)
    print(f"ok: ports — {len(seen)} уникальных портов, все на 127.0.0.1")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Проверка фиксации образов**

Создать `scripts/check_image_pins.py`:

```python
#!/usr/bin/env python3
"""Read-only проверка: образы в deploy зафиксированы по тегу или digest."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
IMAGE = re.compile(r"^\s*image:\s*([^\s#]+)")
GLITCHTIP_EXEMPT = "${GLITCHTIP_IMAGE:-glitchtip/glitchtip:latest}"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def main():
    base = ROOT / "deploy"
    if not base.is_dir():
        fail_all(["нет каталога deploy"])
    errors = []
    checked = 0
    for path in sorted(base.rglob("*.yml")):
        rel = path.relative_to(ROOT)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = IMAGE.match(line)
            if not match:
                continue
            checked += 1
            image = match.group(1).strip("\"'")
            if image == GLITCHTIP_EXEMPT:
                continue
            if "@sha256:" in image:
                continue
            if ":" not in image or image.rsplit(":", 1)[1] == "latest":
                errors.append(f"{rel}:{number}: образ без фиксированной версии: {image}")
    if errors:
        fail_all(errors)
    print(f"ok: image pins — {checked} образов зафиксированы")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Рецепты и verify**

В `justfile` строку `verify:` заменить: `... api-check config-lint workflows-lint ...` → `... api-check config-lint check-env-contract check-ports check-image-pins workflows-lint ...`.

После рецепта `check-host-config` добавить:

```just
# Read-only контракт переменных окружения: только имена, без значений.
check-env-contract:
    python3 scripts/check_env_contract.py

# Read-only карта портов compose: без запуска сервисов.
check-ports:
    python3 scripts/check_ports.py

# Read-only проверка фиксации образов: latest запрещён.
check-image-pins:
    python3 scripts/check_image_pins.py
```

- [ ] **Step 5: Позитивы и негативы**

```bash
chmod +x scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py
python3 -m py_compile scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py
python3 scripts/check_env_contract.py
python3 scripts/check_ports.py
python3 scripts/check_image_pins.py
uvx --from rust-just just --list
```

Expected: три `ok:`-строки; `just --list` показывает три новых рецепта.

Негативы на временной копии:

```bash
TMP=$(mktemp -d)
cp -a deploy .github scripts justfile docs apps "$TMP"/
printf '\n${SREDA_UNKNOWN_VAR}\n' >> "$TMP/justfile"
python3 scripts/check_env_contract.py "$TMP"; echo "env_rc=$?"
printf '      - "0.0.0.0:3000:3000"\n' >> "$TMP/deploy/observability/docker-compose.yml"
python3 scripts/check_ports.py "$TMP"; echo "ports_rc=$?"
printf '    image: nginx:latest\n' >> "$TMP/deploy/observability/docker-compose.yml"
python3 scripts/check_image_pins.py "$TMP"; echo "images_rc=$?"
rm -rf "$TMP"
```

Expected: `env_rc=1`, `ports_rc=1`, `images_rc=1`; сообщения содержат имя переменной/порт/образ, но не значения секретов.

- [ ] **Step 6: Коммит**

```bash
git add scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py justfile
git commit -F- <<'MSG'
chore(devops): add configuration hygiene checks

Добавлены три read-only проверки гигиены конфигурации в observability/foundation.
verify расширен, но прод-флаги и сервисы не включались; serv и чужие ветки не тронуты.

- check_env_contract.py: каждый ${VAR} в deploy/, .github/, scripts/ и justfile
  обязан быть объявлен в .env.example или docs/SECRET-ROTATION.md; локальные
  shell-переменные и SREDA_SITE_URL перечислены в явном списке. Печатаются
  только имена, никогда не значения.
- check_ports.py: сверяет ожидаемую карту dev/prod портов, требует 127.0.0.1
  и отсутствия дублей в каждом compose-файле.
- check_image_pins.py: запрещает latest; единственное документированное
  исключение — glitchtip/glitchtip:latest под профилем errors до выбора релиза.
- Рецепты добавлены в justfile, три имени добавлены в verify после config-lint.

Проверки: py_compile, позитивы, негативы (неизвестная переменная, порт
0.0.0.0, nginx:latest) — все FAIL с exit 1, just --list, check.py,
config_lint.py.

Refs: #9 #26
MSG
```

---

### Task 3: Операционная политика и ресурсный бюджет

**Files:**
- Create: `scripts/check_ops_policy.py`
- Create: `docs/resource-budget.md`
- Modify: `justfile` — `check-ops-policy` в `verify` после `check-image-pins`
- Modify: `mkdocs.yml` — строка в разделе «Эксплуатация» после `SLO и восстановление`
- Modify: `docs/DEVOPS-STATUS.md` — одна строка в разделе «Ссылки»

- [ ] **Step 1: Скрипт политики**

Создать `scripts/check_ops_policy.py`:

```python
#!/usr/bin/env python3
"""Read-only проверка операционной политики: backup, ресурсы и логи."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
OBS = ROOT / "deploy/observability"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def read(rel):
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail_all([f"{rel}: не удалось прочитать: {exc}"])


def main():
    errors = []

    timer = read("deploy/observability/backup.timer")
    if "OnCalendar=daily" not in timer:
        errors.append("backup.timer: нужен OnCalendar=daily")

    try:
        slo = json.loads((OBS / "slo.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail_all([f"slo.json: не удалось прочитать: {exc}"])
    if slo.get("backup_freshness_hours") != 24:
        errors.append("slo.json: backup_freshness_hours должен быть 24")

    restore = read("scripts/restore-observability.sh")
    if "CONFIRM=1" not in restore:
        errors.append("restore-observability.sh: нет guard CONFIRM=1")

    env = read("deploy/observability/.env.example")
    for name in ("SREDA_BACKUP_AGE_RECIPIENT", "SREDA_BACKUP_AGE_IDENTITY"):
        if name not in env:
            errors.append(f".env.example: нет имени {name}")

    backup = read("scripts/backup-observability.sh")
    if "sha256sum" not in backup or "MANIFEST" not in backup:
        errors.append("backup-observability.sh: нет манифеста SHA256")

    try:
        rules = yaml.safe_load(read("deploy/observability/grafana-provisioning/alerting/rules.yml"))
    except yaml.YAMLError as exc:
        fail_all([f"rules.yml: не удалось прочитать YAML: {exc}"])
    stale = None
    groups = rules.get("groups") if isinstance(rules, dict) else None
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("rules"), list):
                continue
            for rule in group["rules"]:
                if isinstance(rule, dict) and rule.get("uid") == "sreda-backup-stale":
                    stale = rule
    if not isinstance(stale, dict):
        errors.append("rules.yml: нет правила sreda-backup-stale")
    else:
        labels = stale.get("labels")
        level = labels.get("enabled", "false") if isinstance(labels, dict) else "false"
        if str(level).lower() != "false":
            errors.append("sreda-backup-stale: правило должно оставаться enabled=false")

    budget_path = ROOT / "docs/resource-budget.md"
    if not budget_path.is_file():
        errors.append("нет docs/resource-budget.md")
    else:
        budget = budget_path.read_text(encoding="utf-8")
        for needle in ("500", "20%", "ADR 0006", "idle", "peak"):
            if needle not in budget:
                errors.append(f"resource-budget.md: нет '{needle}'")

    compose = read("deploy/observability/docker-compose.yml")
    if "profiles:" not in compose or "logs" not in compose:
        errors.append("docker-compose.yml: метричные сервисы должны оставаться под профилем logs")
    if "DJANGO_DEBUG=1" in compose:
        errors.append("docker-compose.yml: DEBUG не должен включаться по умолчанию")

    api_env = read("apps/cms-api/.env.example")
    if "LOG_LEVEL=INFO" not in api_env:
        errors.append("cms-api/.env.example: LOG_LEVEL по умолчанию должен быть INFO")
    for flag in ("RAW_BODY", "LOG_RAW", "CAPTURE_BODY"):
        if flag in compose:
            errors.append(f"docker-compose.yml: флаг {flag} захвата raw body запрещён")

    if errors:
        fail_all(errors)
    print("ok: ops policy — backup, resource gate и логирование согласованы")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Документ бюджета**

Создать `docs/resource-budget.md` ровно с этим содержимым:

```markdown
# Ресурсный бюджет и gate метрик

Документ фиксирует ограничения, при которых метричный контур можно включить.
Основание: ADR 0006 §4, ADR 0005. Решение принимает Илья; DevOps только
подготавливает конфигурацию и измерения.

| Ограничение | Значение | Комментарий |
| --- | --- | --- |
| Стоимость VPS | около 500 ₽/месяц | Превышение требует отдельного решения. |
| Запас RAM | не менее 20% | Измеряется после включения всех штатных сервисов. |
| Prometheus/node_exporter/blackbox_exporter | профиль `logs` | По умолчанию не поднимаются. |
| GLITCHTIP | профиль `errors` | Версия образа выбирается отдельно. |

## Порядок измерения

1. Измерить idle: потребление CPU/RAM и диск в течение суток без метрик.
2. Измерить peak: тот же набор показателей под нагрузкой витрины и CMS API.
3. Сравнить результат с таблицей; только при запасе RAM не менее 20% и
   сохранении бюджета около 500 ₽/месяц подготовить предложение об включении.
4. Получить решение Ильи по ADR 0006 §4 и отдельным коммитом включить
   `docker compose --profile logs up -d`. До этого метрики остаются выключенными.

Внешняя проба `sreda-external` хранится в шаблоне с переменной адреса и не
добавляется в активный scrape-конфиг до появления тестового адреса.
```

- [ ] **Step 3: Рецепт, nav и ссылка**

В `justfile` заменить часть verify `check-ports check-image-pins workflows-lint` на `check-ports check-image-pins check-ops-policy workflows-lint`.

После рецепта `check-image-pins` добавить:

```just
# Read-only политика: backup, ресурсный gate и дефолты логирования.
check-ops-policy:
    uv run --with pyyaml==6.0.4 python scripts/check_ops_policy.py
```

В `mkdocs.yml` после строки `      - SLO и восстановление: slo.md` добавить:

```yaml
      - Ресурсный бюджет: resource-budget.md
```

В `docs/DEVOPS-STATUS.md` в разделе «Ссылки» после строки про `BACKUP-KEY-ROTATION.md` добавить:

```markdown
- `docs/resource-budget.md` — лимиты и gate включения метрик по ADR 0006 §4.
```

- [ ] **Step 4: Проверки**

```bash
chmod +x scripts/check_ops_policy.py
python3 -m py_compile scripts/check_ops_policy.py
uv run --with pyyaml==6.0.4 python scripts/check_ops_policy.py
python3 scripts/check_links.py
uvx --from rust-just just --list
```

Expected: `ok: ops policy — backup, resource gate и логирование согласованы`; `check_links` зелёный; новый рецепт виден в списке.

Негатив:

```bash
TMP=$(mktemp -d)
cp -a deploy docs scripts apps "$TMP"/
printf 'OnCalendar=monthly\n' > "$TMP/deploy/observability/backup.timer"
uv run --with pyyaml==6.0.4 python scripts/check_ops_policy.py "$TMP"; echo "ops_rc=$?"
rm -rf "$TMP"
```

Expected: `ops_rc=1`, сообщение про `OnCalendar=daily`.

- [ ] **Step 5: Коммит**

```bash
git add scripts/check_ops_policy.py docs/resource-budget.md justfile mkdocs.yml docs/DEVOPS-STATUS.md
git commit -F- <<'MSG'
docs(devops): add operational policy checks

Добавлена read-only проверка операционной политики в observability/foundation.
serv, github-настройки, флаги и алерты не трогались; новый PR не создавался.

- check_ops_policy.py проверяет три блока: backup.timer daily, свежесть 24ч из
  slo.json, guard CONFIRM=1, age-имена в .env.example, манифест SHA256 и
  выключенное правило sreda-backup-stale; ресурсный gate ADR 0006 §4;
  LOG_LEVEL=INFO по умолчанию и отсутствие raw body/DEBUG в проде.
- docs/resource-budget.md фиксирует бюджет около 500 ₽/месяц, запас RAM 20%,
  порядок измерения idle/peak и что решение об включении метрик остаётся за Ильёй.
- Рецепт check-ops-policy добавлен в verify после проверок гигиены; документ
  добавлен в mkdocs.yml и в список ссылок DEVOPS-STATUS.md.

Проверки: py_compile, позитив ok, негатив с OnCalendar=monthly (FAIL, exit 1),
check_links.py, just --list.

Refs: #9 #14
MSG
```

---

### Task 4: Мета-линт процесса

**Files:**
- Create: `scripts/check_commit_messages.py`
- Create: `scripts/check_issue_hygiene.py`
- Modify: `justfile` — рецепты `check-commits` и `check-issues` вне `verify`

- [ ] **Step 1: Проверка сообщений коммитов**

Создать `scripts/check_commit_messages.py`:

```python
#!/usr/bin/env python3
"""Read-only проверка conventional commit и подробного тела новых коммитов."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
SUBJECT = re.compile(
    r"^(feat|fix|docs|chore|ci|refactor|test|build|perf|style|revert)(\(.+\))?: .+"
)
REFS = re.compile(r"^Refs:\s*\S+", re.M)


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def git(*args):
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return proc if proc.returncode == 0 else None


def main():
    if git("rev-parse", "--verify", "origin/main") is None:
        print("SKIP: origin/main недоступен")
        return
    rev_list = git("rev-list", "origin/main..HEAD")
    if rev_list is None:
        fail_all(["git rev-list origin/main..HEAD не удался"])
    shas = rev_list.stdout.split()
    errors = []
    for sha in shas:
        message = git("show", "-s", "--format=%B", sha)
        if message is None:
            errors.append(f"{sha[:7]}: не удалось прочитать сообщение")
            continue
        lines = message.stdout.strip().splitlines()
        subject = lines[0] if lines else ""
        body = "\n".join(lines[1:]).strip()
        if not SUBJECT.match(subject):
            errors.append(f"{sha[:7]}: subject не conventional commit: {subject}")
        if not body:
            errors.append(f"{sha[:7]}: пустое тело коммита")
        elif not REFS.search(body):
            errors.append(f"{sha[:7]}: нет строки Refs:")
    if errors:
        fail_all(errors)
    print(f"ok: commit messages — {len(shas)} коммитов, subject/тело/Refs на месте")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Гигиена issue**

Создать `scripts/check_issue_hygiene.py`:

```python
#!/usr/bin/env python3
"""Read-only отчёт о карточках без label/assignee и с давним обновлением."""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
REPO = "Sreda-Media/sreda-media"
DAYS = 30


def fail(message):
    raise SystemExit(f"FAIL: {message}")


def main():
    try:
        proc = subprocess.run(
            [
                "gh", "issue", "list", "--repo", REPO, "--state", "open",
                "--limit", "100", "--json", "number,title,labels,assignees,updatedAt",
            ],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("SKIP: gh недоступен")
        return
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["gh issue list недоступен"])[0]
        print(f"SKIP: {first}")
        return
    try:
        issues = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        fail(f"не удалось разобрать ответ gh: {exc}")

    now = datetime.now(timezone.utc)
    remarks = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        problems = []
        if not issue.get("labels"):
            problems.append("без label")
        if not issue.get("assignees"):
            problems.append("без assignee")
        raw = str(issue.get("updatedAt", "")).replace("Z", "+00:00")
        try:
            updated = datetime.fromisoformat(raw)
            age = (now - updated).days
            if age > DAYS:
                problems.append(f"обновлён {age} дн назад")
        except ValueError:
            problems.append("некорректная дата обновления")
        if problems:
            remarks.append(f"#{issue.get('number')} {issue.get('title')}: " + ", ".join(problems))

    for line in remarks:
        print(line)
    print(f"ok: issue hygiene — {len(issues)} открытых карточек, замечаний {len(remarks)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Рецепты вне verify**

После рецепта `check-issues` в `justfile` (создать оба после `check-github-policy`) добавить:

```just
# Read-only проверка новых коммитов: subject, тело и Refs.
check-commits:
    python3 scripts/check_commit_messages.py

# Read-only отчёт о гигиене открытых issue; ничего не меняет в GitHub.
check-issues:
    python3 scripts/check_issue_hygiene.py
```

`verify` НЕ трогать.

- [ ] **Step 4: Проверки**

```bash
chmod +x scripts/check_commit_messages.py scripts/check_issue_hygiene.py
python3 -m py_compile scripts/check_commit_messages.py scripts/check_issue_hygiene.py
python3 scripts/check_commit_messages.py
python3 scripts/check_issue_hygiene.py
uvx --from rust-just just --list
```

Expected: `ok: commit messages — N коммитов...`; `ok: issue hygiene ...` или `SKIP: gh недоступен`; `just --list` показывает новые рецепты.

Негатив для коммитов:

```bash
TMP=$(mktemp -d)
git init -q "$TMP"
cd "$TMP"
git config user.email test@example.invalid
git config user.name Test
printf a > a.txt && git add a.txt && git commit -qm 'bad message'
python3 /home/deb/Projects/Колледж/sreda-media/scripts/check_commit_messages.py "$TMP"; echo "commits_rc=$?"
cd - >/dev/null
rm -rf "$TMP"
```

Expected: `SKIP: origin/main недоступен`, `commits_rc=0` — корректное поведение без remote. Для проверки FAIL в той же временной копии создать локальную ветку `origin/main`, затем коммит без строки `Refs:`; ожидается `commits_rc=1`.

- [ ] **Step 5: Коммит**

```bash
git add scripts/check_commit_messages.py scripts/check_issue_hygiene.py justfile
git commit -F- <<'MSG'
chore(devops): add process meta-lint checks

Добавлены две read-only проверки процесса в observability/foundation. История
коммитов и чужие issue не изменяются; GitHub не модифицируется; новый PR не создан.

- check_commit_messages.py разбирает только origin/main..HEAD и требует
  conventional subject, непустое тело и строку Refs:. Без origin/main — SKIP.
- check_issue_hygiene.py читает gh issue list и печатает карточки без
  label/assignee или с обновлением старше 30 дней. Без gh/сети — SKIP с exit 0.
- Рецепты check-commits и check-issues добавлены в justfile вне verify и CI.

Проверки: py_compile, позитивы, SKIP-сценарии, just --list, check.py,
config_lint.py.

Refs: #9 #26
MSG
```

---

### Task 5: Документация, полная верификация и push

**Files:**
- Modify: `CONTRIBUTING.md` — новые проверки в `verify` и в списке неблокирующих
- Modify: `docs/DEVOPS-STATUS.md` — строки проверок и пояснение вердикта `NO-GO`
- Modify: `mkdocs.yml` — только если нужно после Task 3

- [ ] **Step 1: CONTRIBUTING.md**

В абзаце про `verify` после упоминания `audit-hardening` и `check-alert-runbooks` добавить: конфигурационные проверки `check-env-contract`, `check-ports`, `check-image-pins` и операционную политику `check-ops-policy`. В абзаце «Остальные рецепты намеренно не входят в verify» добавить `just release-readiness`, `just check-commits` и `just check-issues` с пометкой, что они read-only и ничего не включают.

- [ ] **Step 2: DEVOPS-STATUS.md**

В таблице «Новые проверки готового контура» добавить ровно семь строк по три ячейки:

| Проверка | Запуск | Суть |
| --- | --- | --- |
| `check-env-contract` | `just verify` | Имена `${VAR}` сверены с шаблонами окружения, значения не печатаются. |
| `check-ports` | `just verify` | Карта портов dev/prod, только `127.0.0.1`, без коллизий. |
| `check-image-pins` | `just verify` | Образы зафиксированы; `latest` запрещён кроме GLITCHTIP. |
| `check-ops-policy` | `just verify` | Backup 24ч, ресурсный gate ADR 0006 §4, дефолты логирования. |
| `release-readiness` | Вручную, вне `verify` и CI | Таблица готовности с вердиктом `READY`/`NO-GO`; ничего не включает. |
| `check-commits` | Вручную, вне `verify` и CI | Subject, тело и `Refs:` новых коммитов. |
| `check-issues` | Вручную, вне `verify` и CI | Read-only отчёт о карточкахах без label/assignee и stale. |

В «Подготовлено, но не включено» добавить строку про `release-readiness`: вердикт `NO-GO` — нормальное состояние до PR #16/Q-1. Раздел «Идеи на потом» оставить без изменений.

- [ ] **Step 3: Статическая верификация**

```bash
set -e
chmod +x scripts/release_readiness.py scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py scripts/check_ops_policy.py scripts/check_commit_messages.py scripts/check_issue_hygiene.py
python3 -m py_compile scripts/release_readiness.py scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py scripts/check_ops_policy.py scripts/check_commit_messages.py scripts/check_issue_hygiene.py
for f in scripts/*.sh; do bash -n "$f"; done
python3 scripts/check.py
python3 scripts/config_lint.py
python3 scripts/check_links.py
python3 scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
uv run --with pyyaml==6.0.4 python scripts/check_workflow_hardening.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_runbooks.py
uv run --with pyyaml==6.0.4 python scripts/check_alerts.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-readiness
git diff --check
grep -rnP '[\x{4e00}-\x{9fff}\x{3040}-\x{30ff}]' docs/superpowers/plans/2026-11-25-devops-readiness-and-hygiene.md scripts/release_readiness.py scripts/check_env_contract.py scripts/check_ports.py scripts/check_image_pins.py scripts/check_ops_policy.py scripts/check_commit_messages.py scripts/check_issue_hygiene.py CONTRIBUTING.md docs/DEVOPS-STATUS.md docs/resource-budget.md || true
```

Если `check_alerts.py` отсутствует, использовать реальное имя `scripts/check_alert_rules.py`.

- [ ] **Step 4: Полный verify**

```bash
set -e
uvx --from rust-just just api-db-up
trap 'uvx --from rust-just just api-db-down >/dev/null 2>&1 || true' EXIT
uvx --from rust-just just verify 2>&1 | tee /tmp/opencode/just-verify-readiness-hygiene.log | tail -25
```

Expected: `just verify: все проверки пройдены`; `build-site` честно пропущен до PR #16; контейнер PostgreSQL остановлен trap'ом.

- [ ] **Step 5: Коммит и пуш**

```bash
git add CONTRIBUTING.md docs/DEVOPS-STATUS.md mkdocs.yml
git commit -F- <<'MSG'
docs: reflect readiness and hygiene checks

Обновлена документация в observability/foundation после добавления семи
read-only проверок. serv, PR #16, ci.yml, check_log_schema.py и любые
прод-флаги не трогались; новый PR не создавался.

- CONTRIBUTING.md: check-env-contract, check-ports, check-image-pins и
  check-ops-policy перечислены в verify; release-readiness, check-commits и
  check-issues — в списке неблокирующих рецептов.
- docs/DEVOPS-STATUS.md: семь новых строк в карте проверок, вердикт NO-GO
  как нормальное состояние до адреса и PR #16.
- Полная верификация: py_compile, bash -n, check.py, config_lint.py,
  check_links.py, check_runbook_commands.py, audit_workflows.py,
  workflow hardening, alert runbooks, actionlint, zizmor, mkdocs strict,
  полный just verify с PostgreSQL 18 на 127.0.0.1:55432.

Refs: #9 #14 #26 #35
MSG
git push origin observability/foundation
```

Если SSH-пуш не проходит, повторить через HTTPS с токеном из `gh auth token`, не печатая токен. Expected: локальный HEAD == remote head; все коммиты плана и спек `1cd212d` на remote; рабочее дерево чистое.

---

### Итоговая проверка

- [ ] Убедиться, что ни один флаг не выставлен: `env | grep '^ENABLE_' || true`, `gh variable list --repo Sreda-Media/sreda-media`, `gh secret list --repo Sreda-Media/sreda-media`.
- [ ] Убедиться, что все алерты выключены: `grep -c 'enabled: "true"' deploy/observability/grafana-provisioning/alerting/rules.yml` → `0`.
- [ ] Убедиться, что PR #16 остаётся открытым и не тронут.
- [ ] Убедиться, что `serv`, `ci.yml`, `check_log_schema.py`, `apps/site` и чужие ветки не изменялись.
