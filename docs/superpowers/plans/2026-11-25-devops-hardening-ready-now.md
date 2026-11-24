# DevOps hardening — ready now Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить в ветку `observability/foundation` хостовые шаблоны как код, SLO/DR-определения, DX-помощников и read-only проверку GitHub-политики, не включая ни одной реальной выкладки или алерта.

**Architecture:** Источник правды лежит в `deploy/` и `docs/`; каждый модуль имеет собственный проверщик в `scripts/`. Детерминированные проверщики только чтения входят в `just verify`, а справочные иopotенциально сетевые остаются отдельными неблокирующими рецептами (`doctor`, `dr-drill`, `check-github-policy`). Ни один шаг не меняет `serv`, `main`, `ci.yml`, `check_log_schema.py`, PR #16 или секреты.

**Tech Stack:** Python 3.14 stdlib, PyYAML через `uv run --with pyyaml==6.0.4`, Bash, `just`, Grafana provisioning (YAML/JSON), systemd unit-файлы, `gh api` только для GET.

---

## Task 1: Хостовая конфигурация как код

**Files:**
- Create: `deploy/host/Caddyfile.template`
- Create: `deploy/host/docker-daemon.json.template`
- Create: `deploy/host/journald-vacuum.service`
- Create: `deploy/host/journald-vacuum.timer`
- Create: `scripts/check_host_config.py`
- Modify: `justfile:6` (добавить `check-host-config` в `verify`), `justfile:59` (новый рецепт)

- [ ] **Step 1: Создать шаблоны конфигурации**

`deploy/host/Caddyfile.template`:

```
{{SREDA_SITE_URL}} {
    root * /srv/sreda/current
    encode gzip zstd
    file_server

    handle_errors {
        rewrite * /404.html
        file_server
    }

    log {
        output stdout
        format json
    }
}
```

`deploy/host/docker-daemon.json.template`:

```
{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
```

`deploy/host/journald-vacuum.service`:

```
[Unit]
Description=Vacuum old journal entries
Documentation=man:journalctl(1)

[Service]
Type=oneshot
ExecStart=/usr/bin/journalctl --vacuum-size=500M --vacuum-time=7d
```

`deploy/host/journald-vacuum.timer`:

```
[Unit]
Description=Weekly journal vacuum

[Timer]
OnCalendar=weekly
Persistent=true
Unit=journald-vacuum.service

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Написать проверщик**

`scripts/check_host_config.py`:

```python
#!/usr/bin/env python3
"""Проверка хостовых шаблонов как кода. Только чтение и временные копии.

Запуск: python3 scripts/check_host_config.py [root]
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    "deploy/host/Caddyfile.template",
    "deploy/host/docker-daemon.json.template",
    "deploy/host/journald-vacuum.service",
    "deploy/host/journald-vacuum.timer",
)


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def skip(msg: str) -> None:
    print(f"skip: {msg}")


def check_files(base: Path) -> None:
    for rel in FILES:
        if not (base / rel).is_file():
            fail(f"нет файла {rel}")


def check_caddy(base: Path) -> str:
    text = (base / FILES[0]).read_text(encoding="utf-8")
    if "{{SREDA_SITE_URL}}" not in text:
        fail("Caddyfile.template: нужен плейсхолдер {{SREDA_SITE_URL}}")
    if "sreda.sielom.ru" in text or "://" in text:
        fail("Caddyfile.template: не храним реальный адрес или схему в шаблоне")
    for needle in ("root * /srv/sreda/current", "file_server", "404.html", "format json"):
        if needle not in text:
            fail(f"Caddyfile.template: нет обязательной строки {needle!r}")
    return text.replace("{{SREDA_SITE_URL}}", "https://sreda.invalid")


def check_daemon(base: Path) -> None:
    raw = (base / FILES[1]).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"docker-daemon.json.template: неверный JSON: {exc}")
    if data.get("log-driver") != "json-file":
        fail("docker-daemon.json.template: log-driver должен быть json-file")
    opts = data.get("log-opts") or {}
    if opts.get("max-size") != "10m" or opts.get("max-file") != "3":
        fail("docker-daemon.json.template: нужны log-opts max-size=10m, max-file=3")


def check_units(base: Path) -> None:
    service = (base / FILES[2]).read_text(encoding="utf-8")
    timer = (base / FILES[3]).read_text(encoding="utf-8")
    if "[Unit]" not in service or "[Service]" not in service:
        fail("journald-vacuum.service: нужны секции [Unit] и [Service]")
    if "--vacuum-size=500M" not in service or "--vacuum-time=7d" not in service:
        fail("journald-vacuum.service: нужны параметры вакуума 500M и 7d")
    for needle in ("[Unit]", "[Timer]", "OnCalendar=weekly", "Persistent=true", "Unit=journald-vacuum.service", "WantedBy=timers.target"):
        if needle not in timer:
            fail(f"journald-vacuum.timer: нет обязательной строки {needle!r}")


def check_tools(base: Path, caddy_text: str) -> None:
    with tempfile.TemporaryDirectory(prefix="sreda-host-check-") as tmp:
        tmpdir = Path(tmp)
        caddy_file = tmpdir / "Caddyfile"
        caddy_file.write_text(caddy_text, encoding="utf-8")
        if shutil.which("caddy"):
            proc = subprocess.run(["caddy", "validate", "--config", str(caddy_file)], capture_output=True, text=True)
            if proc.returncode != 0:
                fail(f"caddy validate: {proc.stderr.strip() or proc.stdout.strip()}")
        else:
            skip("caddy не установлен: caddy validate не запускался")
        if shutil.which("systemd-analyze"):
            units = [tmpdir / Path(rel).name for rel in FILES[2:]]
            for src, dst in zip(FILES[2:], units):
                shutil.copy2(base / src, dst)
            proc = subprocess.run(["systemd-analyze", "verify", *map(str, units)], capture_output=True, text=True)
            if proc.returncode != 0:
                fail(f"systemd-analyze verify: {proc.stderr.strip() or proc.stdout.strip()}")
        else:
            skip("systemd-analyze не найден: проверка юнитов не запускалась")


def main() -> None:
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    check_files(base)
    caddy_text = check_caddy(base)
    check_daemon(base)
    check_units(base)
    check_tools(base, caddy_text)
    print("ok: host config — Caddy, docker daemon и journald vacuum подготовлены")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Проверить позитивный и негативный сценарии**

Run: `python3 scripts/check_host_config.py`
Expected: `ok: host config — Caddy, docker daemon и journald vacuum подготовлены` (или строки `skip:` для отсутствующих инструментов).

Run: `TMP=$(mktemp -d); cp -a deploy/host "$TMP/host"; sed -i 's/{{SREDA_SITE_URL}}/{{BROKEN}}/' "$TMP/host/Caddyfile.template"; python3 scripts/check_host_config.py "$TMP"; echo "exit=$?"`
Expected: `FAIL: Caddyfile.template: нужен плейсхолдер {{SREDA_SITE_URL}}` и `exit=1`.

Run: `rm -rf "$TMP"`
Expected: временный каталог удалён.

- [ ] **Step 4: Добавить рецепт в justfile**

В строке `verify:` заменить `check check-logs check-alerts check-uptime` на `check check-logs check-alerts check-uptime check-host-config`.

После рецепта `check-uptime` добавить:

```
# Хостовые шаблоны Caddy/Docker/journald как код.
check-host-config:
    python3 scripts/check_host_config.py
```

- [ ] **Step 5: Закоммитить**

```bash
git add deploy/host scripts/check_host_config.py justfile
git commit -F- <<'MSG'
chore(devops): add host config templates and checker

Шаблоны Caddy/Docker daemon/journald vacuum хранятся в deploy/host как код.
Проверщик не трогает serv: он работает с репозиторием и временными копиями,
проверяет плейсхолдер адреса и валидирует caddy/systemd только при наличии
инструментов. Рецепт check-host-config добавлен в just verify.

Refs: #9 #14
MSG
```

---

## Task 2: SLO, дашборд и DR-репетиция

**Files:**
- Create: `docs/slo.md`
- Create: `deploy/observability/slo.json`
- Create: `deploy/observability/grafana-dashboards/slo.json`
- Modify: `deploy/observability/grafana-provisioning/alerting/rules.yml` (добавить 3 правила в конец существующей группы `sreda-logs`)
- Create: `scripts/check_slo.py`
- Create: `scripts/dr-drill.sh`
- Modify: `justfile` (рецепты `check-slo`, `dr-drill`, включение `check-slo` в verify)

- [ ] **Step 1: Машиночитаемое определение SLO**

`deploy/observability/slo.json`:

```
{
  "availability": {
    "target_percent": 99,
    "window_days": 30,
    "burn_rate_fast": 14.4,
    "burn_rate_slow": 6
  },
  "latency_p95_ms": 800,
  "backup_freshness_hours": 24,
  "rto_minutes": 15,
  "rpo_hours": 24,
  "dashboard_uid": "sreda-slo",
  "rule_uids": [
    "sreda-slo-fast-burn",
    "sreda-slo-slow-burn",
    "sreda-backup-stale"
  ]
}
```

- [ ] **Step 2: Документ SLO**

`docs/slo.md`:

```
# SLO и цели восстановления

Цифры в этом файле дублируются в `deploy/observability/slo.json` — он является
машиночитаемым источником для проверок и дашборда.

## SLI

- **Доступность:** доля успешных проверок `probe_success` за скользящие 30 дней.
- **Задержка:** 95-й перцентиль времени отдачи главной страницы, цель 800 мс.
- **Свежесть бэкапа:** время с последнего успешного `backup-observability.sh`.

## SLO

- Доступность: **99% за 30 дней**. Error budget — 0.3% времени простоя (около 2 ч 10 мин за месяц).
- Быстрое сгорание: burn rate **14.4** (1 час / 5 минут).
- Медленное сгорание: burn rate **6** (6 часов / 30 минут).
- Бэкап считается свежим, если последний успех был не старше **24 ч**.

## Восстановление

- RTO: **15 минут** (переключение симлинка `current` на предыдущий релиз).
- RPO: **24 часа** (ежедневный systemd-таймер backup).
- Репетиция: `just dr-drill` — только во временном каталоге, без `/srv` и systemd.

Правила алертов подготовлены с `enabled="false"` и включаются отдельным
изменением после PR #16 и Q-1. Ссылка: [мониторинг](../../monitoring.md).
```

Все значения в документе совпадают с `deploy/observability/slo.json`.

- [ ] **Step 3: Дашборд**

`deploy/observability/grafana-dashboards/slo.json`:

```
{
  "uid": "sreda-slo",
  "title": "Sreda SLO",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "Availability 30d (%)",
      "targets": [{"refId": "A", "expr": "avg_over_time(probe_success{job=\"sreda\"}[30d]) * 100"}],
      "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
    },
    {
      "id": 2,
      "type": "stat",
      "title": "Latency p95 (ms)",
      "targets": [{"refId": "B", "expr": "histogram_quantile(0.95, sum(rate(sreda_request_duration_seconds_bucket[5m])) by (le)) * 1000"}],
      "gridPos": {"h": 8, "w": 6, "x": 6, "y": 0}
    },
    {
      "id": 3,
      "type": "stat",
      "title": "Backup age (hours)",
      "targets": [{"refId": "C", "expr": "time() - backup_last_success_timestamp"}],
      "gridPos": {"h": 8, "w": 6, "x": 12, "y": 0}
    },
    {
      "id": 4,
      "type": "stat",
      "title": "Error budget remaining (%)",
      "targets": [{"refId": "D", "expr": "clamp_min((1 - (1 - avg_over_time(probe_success{job=\"sreda\"}[30d])) / 0.01) * 100, 0)"}],
      "gridPos": {"h": 8, "w": 6, "x": 18, "y": 0}
    }
  ]
}
```

- [ ] **Step 4: Добавить три выключенных правила SLO**

Дописать в `deploy/observability/grafana-provisioning/alerting/rules.yml` после последнего правила группы `sreda-logs`, сохранив отступ 8 пробелов для `- uid:`:

```
      - uid: sreda-slo-fast-burn
        title: SLO — быстрое сгорание error budget
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            model:
              expr: avg_over_time(probe_success{job="sreda"}[1h]) < 0.856
              queryType: instant
              refId: A
          - refId: B
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator: {params: [0], type: gt}
                  operator: {type: and}
                  query: {params: [A]}
                  reducer: {type: last}
                  type: query
              datasource: {type: __expr__, uid: __expr__}
              expression: A
              intervalMs: 1000
              maxDataPoints: 43200
              refId: B
              type: reduce
        noDataState: NoData
        execErrState: Error
        for: 5m
        annotations:
          summary: Доступность за час ниже порога быстрого сгорания
          description: Сравнить с slo.json и проверить выкладку.
        labels:
          severity: critical
          component: slo
          enabled: "false"

      - uid: sreda-slo-slow-burn
        title: SLO — медленное сгорание error budget
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            model:
              expr: avg_over_time(probe_success{job="sreda"}[6h]) < 0.94
              queryType: instant
              refId: A
          - refId: B
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator: {params: [0], type: gt}
                  operator: {type: and}
                  query: {params: [A]}
                  reducer: {type: last}
                  type: query
              datasource: {type: __expr__, uid: __expr__}
              expression: A
              intervalMs: 1000
              maxDataPoints: 43200
              refId: B
              type: reduce
        noDataState: NoData
        execErrState: Error
        for: 30m
        annotations:
          summary: Доступность за 6 часов ниже порога медленного сгорания
          description: Запланировать разбор до исчерпания error budget.
        labels:
          severity: warning
          component: slo
          enabled: "false"

      - uid: sreda-backup-stale
        title: Бэкап старше 24 часов
        condition: B
        data:
          - refId: A
            datasourceUid: prometheus
            model:
              expr: time() - backup_last_success_timestamp > 24 * 3600
              queryType: instant
              refId: A
          - refId: B
            datasourceUid: __expr__
            model:
              conditions:
                - evaluator: {params: [0], type: gt}
                  operator: {type: and}
                  query: {params: [A]}
                  reducer: {type: last}
                  type: query
              datasource: {type: __expr__, uid: __expr__}
              expression: A
              intervalMs: 1000
              maxDataPoints: 43200
              refId: B
              type: reduce
        noDataState: NoData
        execErrState: Error
        for: 10m
        annotations:
          summary: Последний успешный бэкап старше 24 часов
          description: Проверить backup.timer и just backup-drill.
        labels:
          severity: warning
          component: backup
          enabled: "false"
```

- [ ] **Step 5: Проверщик SLO**

`scripts/check_slo.py`:

```python
#!/usr/bin/env python3
"""Сверка slo.json, docs/slo.md, дашборда и правил алертов.

Запуск: uv run --with pyyaml==6.0.4 python scripts/check_slo.py
"""
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit(f"FAIL: нужен PyYAML (uv run --with pyyaml==6.0.4 ...): {exc}")

ROOT = Path(__file__).resolve().parent.parent
SLO = ROOT / "deploy/observability/slo.json"
DOC = ROOT / "docs/slo.md"
DASH = ROOT / "deploy/observability/grafana-dashboards/slo.json"
RULES = ROOT / "deploy/observability/grafana-provisioning/alerting/rules.yml"


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    for path in (SLO, DOC, DASH, RULES):
        if not path.is_file():
            fail(f"нет файла {path.relative_to(ROOT)}")
    slo = json.loads(SLO.read_text(encoding="utf-8"))
    doc = DOC.read_text(encoding="utf-8")
    dash = json.loads(DASH.read_text(encoding="utf-8"))
    data = yaml.safe_load(RULES.read_text(encoding="utf-8"))

    if slo.get("availability", {}).get("target_percent") != 99:
        fail("slo.json: target_percent должен быть 99")
    if slo.get("availability", {}).get("window_days") != 30:
        fail("slo.json: window_days должен быть 30")
    if slo.get("latency_p95_ms") != 800:
        fail("slo.json: latency_p95_ms должен быть 800")
    if slo.get("backup_freshness_hours") != 24 or slo.get("rpo_hours") != 24:
        fail("slo.json: свежесть бэкапа и RPO должны быть 24")
    if slo.get("rto_minutes") != 15:
        fail("slo.json: rto_minutes должен быть 15")
    for token in ("99%", "30", "800", "24", "15"):
        if token not in doc:
            fail(f"docs/slo.md: нет значения {token!r}")
    if dash.get("uid") != slo.get("dashboard_uid"):
        fail("дашборд slo.json: uid не совпадает с dashboard_uid")
    if len(dash.get("panels", [])) != 4:
        fail("дашборд slo.json: ожидается 4 панели")

    uids = {r.get("uid") for g in data.get("groups", []) for r in g.get("rules", [])}
    for uid in slo.get("rule_uids", []):
        if uid not in uids:
            fail(f"rules.yml: нет правила {uid}")
        rule = next(r for g in data["groups"] for r in g["rules"] if r.get("uid") == uid)
        if rule.get("labels", {}).get("enabled") != "false":
            fail(f"{uid}: labels.enabled должен быть \"false\"")
    print("ok: SLO — цели, дашборд и три выключенных правила согласованы")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: DR-репетиция**

`scripts/dr-drill.sh`:

```bash
#!/usr/bin/env bash
# Репетиция DR без `/srv` и systemd: только временные копии конфигурации.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

rpo=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rpo_hours"])' "$REPO_ROOT/deploy/observability/slo.json")
if [ "$rpo" -gt 24 ]; then
    printf '[dr-drill] FAIL: RPO %s ч больше 24 ч\n' "$rpo" >&2
    exit 1
fi

for rel in deploy/observability/backup.service deploy/observability/backup.timer scripts/backup-observability.sh scripts/restore-observability.sh; do
    cp "$REPO_ROOT/$rel" "$tmp/$(basename "$rel")"
done
grep -q 'CONFIRM=1' "$tmp/restore-observability.sh" || { echo '[dr-drill] FAIL: нет guard CONFIRM=1' >&2; exit 1; }
grep -q 'OnCalendar=daily' "$tmp/backup.timer" || { echo '[dr-drill] FAIL: backup.timer не ежедневный' >&2; exit 1; }
if grep -RqsE '/srv/sreda|systemctl (start|stop|enable|disable)' "$tmp"; then
    echo '[dr-drill] FAIL: репетиция не должна трогать /srv или systemd' >&2
    exit 1
fi
printf '[dr-drill] OK: RPO=%s ч, backup.timer daily, restore guard CONFIRM=1, временный каталог удалён\n' "$rpo"
```

Комментарий первой строки уже описывает репетицию без обращения к `/srv` и systemd.

- [ ] **Step 7: Проверить сценарии**

Run: `uv run --with pyyaml==6.0.4 python scripts/check_slo.py`
Expected: `ok: SLO — цели, дашборд и три выключенных правила согласованы`.

Run: `uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py`
Expected: `ok: Grafana alerting — контактов ..., правил 10, все отключены (enabled=false), секреты через env` (было 7, стало 10).

Run: `TMP=$(mktemp -d); cp deploy/observability/slo.json "$TMP/slo.json"; python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p)); d["rto_minutes"]=60; json.dump(d,open(p,"w"))' "$TMP/slo.json"; sed -i "s|deploy/observability/slo.json|$TMP/slo.json|" /dev/null; echo "negative target=$TMP/slo.json"`
Expected: путь сохранён для ручной порчи в следующем шаге.

Negative: временно заменить `deploy/observability/slo.json` скопированной версией с `rto_minutes: 60`, запустить `uv run --with pyyaml==6.0.4 python scripts/check_slo.py`, ожидать `FAIL: slo.json: rto_minutes должен быть 15`, затем восстановить оригинал из `$TMP/slo.json` и повторить позитивный прогон.

Run: `bash scripts/dr-drill.sh`
Expected: `OK: RPO=24 ч, backup.timer daily, restore guard CONFIRM=1, временный каталог удалён`.

- [ ] **Step 8: Рецепты justfile**

В `verify:` добавить `check-slo` после `check-host-config`.

После рецепта `check-host-config` добавить:

```
# Сверка SLO, дашборда и выключенных правил.
check-slo:
    uv run --with pyyaml==6.0.4 python scripts/check_slo.py

# DR-репетиция во временном каталоге, без /srv и systemd.
dr-drill:
    bash scripts/dr-drill.sh
```

- [ ] **Step 9: Закоммитить**

```bash
git add docs/slo.md deploy/observability scripts/check_slo.py scripts/dr-drill.sh justfile
git commit -F- <<'MSG'
chore(devops): define SLO, dashboard and DR drill

Добавлены машиночитаемые цели deploy/observability/slo.json, документ docs/slo.md,
дашборд uid sreda-slo и три новых правила (быстрый/медленный burn rate, свежесть
бэкапа). Все правила остаются enabled=false до PR #16 и Q-1. check_slo.py сверяет
 согласованность между источниками и входит в verify; dr-drill.sh репетирует восстановление
только во временном каталоге, не трогая /srv и systemd.

Refs: #9 #14
MSG
```

---

## Task 3: DX-помощники

**Files:**
- Create: `scripts/doctor.sh`
- Create: `scripts/check_runbook_commands.py`
- Create: `scripts/audit_workflows.py`
- Modify: `justfile` (рецепты `doctor`, `check-runbook`, `audit-workflows`; включение последних двух в verify)

- [ ] **Step 1: Doctor**

`scripts/doctor.sh`:

```bash
#!/usr/bin/env bash
# Диагностика локального инструментария. Никогда не падает: это справка, не гейд.
set -uo pipefail
printf '%-18s %s\n' 'ИНСТРУМЕНТ' 'ВЕРСИЯ'
for name in python3 uv pnpm node go just gh docker caddy systemd-analyze gitleaks cosign; do
    if command -v "$name" >/dev/null 2>&1; then
        version=$("$name" --version 2>/dev/null | head -n 1 || true)
        printf '%-18s %s\n' "$name" "${version:-установлен}"
    else
        printf '%-18s %s\n' "$name" 'не найден'
    fi
done
exit 0
```

- [ ] **Step 2: Проверка команд в документации**

`scripts/check_runbook_commands.py`:

```python
#!/usr/bin/env python3
"""Сверяет just-рецепты и scripts/* из bash-блоков docs/*.md с репозиторием."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"```(?:bash|sh)\s*\n(.*?)```", re.S | re.I)
JUST = re.compile(r"\bjust\s+([A-Za-z0-9_-]+)")
SCRIPT = re.compile(r"\bscripts/([A-Za-z0-9_./-]+\.(?:sh|py))\b")
JUST_RECIPE = re.compile(r"^([A-Za-z0-9_-]+)(?:\s+[^:]*)?:", re.M)


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    recipes = set(JUST_RECIPE.findall(justfile))
    bad = []
    checked_just = 0
    checked_scripts = 0
    for doc in sorted((ROOT / "docs").rglob("*.md")):
        for block in FENCE.findall(doc.read_text(encoding="utf-8", errors="replace")):
            for line in block.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for recipe in JUST.findall(line):
                    checked_just += 1
                    if recipe not in recipes:
                        bad.append(f"{doc.relative_to(ROOT)}: нет just-рецепта {recipe!r}")
                for script in SCRIPT.findall(line):
                    checked_scripts += 1
                    if not (ROOT / "scripts" / script).is_file():
                        bad.append(f"{doc.relative_to(ROOT)}: нет scripts/{script}")
    if bad:
        for line in bad[:50]:
            print(line)
        fail(f"проверка команд в docs: {len(bad)} ошибок")
    print(f"ok: docs commands — just {checked_just}, scripts {checked_scripts}, всё существует")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Аудит pin-ов workflow**

`scripts/audit_workflows.py`:

```python
#!/usr/bin/env python3
"""Требует, чтобы внешние uses: были зафиксированы по 40-символьному SHA."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA = re.compile(r"@[0-9a-f]{40}$")


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    bad = []
    count = 0
    for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
        for lineno, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if not match:
                continue
            value = match.group(1)
            count += 1
            if value.startswith("./"):
                continue
            if not SHA.search(value):
                bad.append(f"{wf.relative_to(ROOT)}:{lineno}: uses {value} без SHA-пина")
    if bad:
        for line in bad[:50]:
            print(line)
        fail(f"workflow pins: {len(bad)} ошибок")
    print(f"ok: workflow pins — {count} uses, внешние зафиксированы по SHA")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Проверить DX-скрипты**

Run: `bash scripts/doctor.sh; echo "exit=$?"`
Expected: таблица с версиями/«не найден», `exit=0`.

Run: `python3 scripts/check_runbook_commands.py`
Expected: `ok: docs commands — just ... , scripts ... , всё существует`.

Negative: добавить в конец `docs/runbook.md` строку `just no-such-recipe` inside bash-блока, запустить проверщик, ожидать `FAIL`, затем откатить строку.

Run: `python3 scripts/audit_workflows.py`
Expected: `ok: workflow pins — ... uses, внешние зафиксированы по SHA`.

Negative: временно заменить один SHA в workflow на `v4`, запустить проверщик, ожидать `FAIL`, восстановить файл.

- [ ] **Step 5: Рецепты justfile**

В `verify:` добавить `check-runbook audit-workflows` после `check-slo`.

После рецепта `dr-drill` добавить:

```
# Диагностика инструментов: справка, всегда exit 0.
doctor:
    bash scripts/doctor.sh

# Проверка команд в bash-блоках документации.
check-runbook:
    python3 scripts/check_runbook_commands.py

# Аудит SHA-пинов внешних GitHub Actions.
audit-workflows:
    python3 scripts/audit_workflows.py
```

- [ ] **Step 6: Закоммитить**

```bash
git add scripts/doctor.sh scripts/check_runbook_commands.py scripts/audit_workflows.py justfile
git commit -F- <<'MSG'
chore(devops): add doctor and documentation/workflow guards

Добавлены три DX-утилиты: doctor.sh печатает состояние инструментов и всегда
возвращает 0; check_runbook_commands.py сверяет just-рецепты и scripts/* внутри
bash-блоков docs; audit_workflows.py требует 40-символьные SHA у внешних uses.
Первая — справочная, остальные включены в just verify и ловят расхождение
документации с фактическими командами и пинами.

Refs: #9 #26 #35
MSG
```

---

## Task 4: Read-only проверка GitHub-политики

**Files:**
- Create: `scripts/check_branch_policy.py`
- Create: `.github/workflows/policy-check.yml`
- Modify: `justfile` (рецепт `check-github-policy` вне verify)

- [ ] **Step 1: Скрипт проверки политики**

`scripts/check_branch_policy.py`:

```python
#!/usr/bin/env python3
"""Read-only сверка защиты main. Ничего не меняет в GitHub."""
import json
import shutil
import subprocess
import sys

REPO = "Sreda-Media/sreda-media"
ENDPOINT = f"repos/{REPO}/branches/main/protection"


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    if not shutil.which("gh"):
        print("skip: gh не установлен, проверка политики пропущена")
        return
    proc = subprocess.run(["gh", "api", ENDPOINT], capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip().splitlines()[:1]
        print(f"skip: gh api недоступен ({detail[0] if detail else 'нет деталей'}), проверка политики пропущена")
        return
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        fail(f"gh api вернул не JSON: {exc}")
    checks = data.get("required_status_checks") or {}
    if checks.get("strict") is not True:
        fail("main: required_status_checks.strict должен быть true")
    contexts = [c.strip() for c in (checks.get("contexts") or [])]
    if "ci" not in contexts:
        fail("main: обязательный контекст 'ci' отсутствует")
    reviews = data.get("required_pull_request_reviews") or {}
    if (reviews.get("required_approving_review_count") or 0) < 1:
        fail("main: требуется минимум одно одобрение")
    print("ok: GitHub policy — strict ci + 1 approval, read-only")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Workflow**

`.github/workflows/policy-check.yml`:

```
name: Policy check (read-only)

# Еженедельная read-only сверка защиты main. Не меняет ruleset и не входит в ci.
on:
  workflow_dispatch:
  schedule:
    - cron: '23 5 * * 1'

permissions:
  contents: read

jobs:
  policy:
    name: Branch protection
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
      - name: Check policy
        env:
          GH_TOKEN: ${{ github.token }}
        run: python3 scripts/check_branch_policy.py
```

- [ ] **Step 3: Проверить**

Run: `python3 scripts/check_branch_policy.py`
Expected: `ok: GitHub policy — strict ci + 1 approval, read-only` или `skip: ...` если нет доступа. Ни одного `PATCH`/`PUT`.

Run: `python3 scripts/audit_workflows.py`
Expected: `ok: workflow pins — ... uses, внешние зафиксированы по SHA` (новый checkout уже с SHA).

- [ ] **Step 4: Рецепт и коммит**

После рецепта `audit-workflows` добавить:

```
# Read-only проверка защиты main (gh api GET, ничего не меняет).
check-github-policy:
    python3 scripts/check_branch_policy.py
```

```bash
git add scripts/check_branch_policy.py .github/workflows/policy-check.yml justfile
git commit -F- <<'MSG'
chore(devops): add read-only branch policy check

Проверщик через gh api GET сверяет, что main требует строгий статус ci и одно
одобрение. При отсутствии gh или доступе он честно пропускает проверку. Workflow
policy-check.yml запускает её по расписанию и вручную, вне обязательного статуса;
никаких PATCH/PUT и изменений правил репозитория нет.

Refs: #9 #44
MSG
```

---

## Task 5: Интеграция в документацию и итоговая верификация

**Files:**
- Modify: `CONTRIBUTING.md:58-64`
- Modify: `docs/DEVOPS-STATUS.md`
- Modify: `mkdocs.yml` (раздел «Эксплуатация»)

- [ ] **Step 1: Обновить CONTRIBUTING.md**

В абзаце про `verify` добавить проверки `check-host-config`, `check-slo`, `check-runbook`, `audit-workflows`. В список неблокирующих рецептов добавить `just doctor`, `just dr-drill`, `just check-github-policy` и пометку, что они ничего не включают и не меняют GitHub.

- [ ] **Step 2: Обновить DEVOPS-STATUS.md**

Добавить таблицу «Новые проверки готового контура» со строками: check-host-config (verify), check-slo (verify), check-runbook (verify), audit-workflows (verify), doctor (отдельно), dr-drill (отдельно), check-github-policy (отдельно, read-only). Из раздела «Идеи на потом» убрать пункты, реализованные этим планом. Упомянуть, что SBOM уже загружается в `supply-chain.yml` повторно добавлять не нужно.

- [ ] **Step 3: Обновить mkdocs.yml**

В раздел «Эксплуатация» после `Ротация секретов` добавить:

```
      - SLO и восстановление: slo.md
```

- [ ] **Step 4: Статическая верификация**

```bash
set -e
chmod +x scripts/check_host_config.py scripts/check_slo.py scripts/dr-drill.sh scripts/doctor.sh scripts/check_runbook_commands.py scripts/audit_workflows.py scripts/check_branch_policy.py
python3 -m py_compile scripts/check_host_config.py scripts/check_slo.py scripts/check_runbook_commands.py scripts/audit_workflows.py scripts/check_branch_policy.py
bash -n scripts/dr-drill.sh scripts/doctor.sh
python3 scripts/check.py
python3 scripts/config_lint.py
uv run --with pyyaml==6.0.4 python scripts/check_alert_rules.py
uv run --with pyyaml==6.0.4 python scripts/check_slo.py
python3 scripts/check_host_config.py
python3 scripts/check_runbook_commands.py
python3 scripts/audit_workflows.py
bash scripts/dr-drill.sh
bash scripts/doctor.sh
/tmp/opencode/bin/actionlint -color
GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-hardening-ready
```

Expected: все проверки зелёные; actionlint — 0 ошибок; zizmor — `No findings to report`; mkdocs strict — ok (info-сообщения о страницах без nav не являются ошибками).

- [ ] **Step 5: Полный гейд с PostgreSQL**

```bash
set -e
uvx --from rust-just just api-db-up
trap 'uvx --from rust-just just api-db-down >/dev/null 2>&1 || true' EXIT
uvx --from rust-just just verify 2>&1 | tee /tmp/opencode/just-verify-hardening-ready.log | tail -25
```

Expected: `just verify: все проверки пройдены`, 44 pytest CMS API, контейнер PostgreSQL остановлен trap-ом.

- [ ] **Step 6: Коммит документации**

```bash
git add CONTRIBUTING.md docs/DEVOPS-STATUS.md mkdocs.yml
git commit -F- <<'MSG'
docs: reflect hardening checks in contributor and status pages

После добавления хостовых шаблонов, SLO/DR, DX-утилит и read-only проверки
политики обновлены CONTRIBUTING.md, docs/DEVOPS-STATUS.md и навигация mkdocs.
Статусная страница теперь показывает, какие проверки вошли в обязательный
verify, а какие остаются отдельными; отмечено, что SBOM уже загружается
существующим supply-chain workflow.

Проверки: check.py, config_lint, check_alert_rules, check_slo,
check_host_config, check_runbook_commands, audit_workflows, dr-drill, doctor,
actionlint, zizmor, mkdocs strict, полный just verify с PostgreSQL 18 на 55432.

Refs: #9 #14 #26 #35
MSG
```
