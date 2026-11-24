# DevOps hardening — after address Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подготовить код и документацию для включения внешних проверок, keyless-подписи и SLO-панелей после появления сайта и адреса; сейчас ничего не включать.

**Architecture:** Все компоненты этого плана находятся за явными гейтами: `SREDA_SITE_URL`, флаги `ENABLE_*`, слияние PR #16 и решение по ADR 0006. Скрипты и workflow создаются заранее, но возвращают успех с сообщением «проверка не настроена», пока гейты не открыты. `verify-artifact.sh` остаётся единой точкой проверки артефакта.

**Tech Stack:** Bash, Python 3 stdlib, GitHub Actions (`workflow_dispatch`, `contents: read`, `id-token: write`), cosign, SLSA provenance, Grafana dashboards JSON.

---

## Гейты включения

| Гейт | Условие | Что разблокирует |
| --- | --- | --- |
| PR #16 | `apps/site` в `main` | Реальная сборка `just build-site`, smoke, Lighthouse |
| Q-1 | Домен, DNS, тестовый адрес | `SREDA_SITE_URL`, мониторы, внешняя точка проверки |
| `ENABLE_DEPLOY=true` | Решение Ильи по ADR 0006 | `dry_run=false` в `deploy.yml` |
| `ENABLE_DOCS_PAGES=true` | Решение по публикации | Публикация MkDocs на Pages |
| `ENABLE_PROVENANCE=true` | Решение по keyless | `provenance.yml` с `id-token: write` |
| ADR 0006 | Финальный хостинг | Все внешние адреса и выкладка |

Ни один флаг в этом плане не выставляется.

---

## Task 1: Синтетическая проверка по адресу

**Files:**
- Create: `scripts/synthetic-check.sh`
- Modify: `justfile` (рецепт `synthetic` вне verify)

- [ ] **Step 1: Скрипт**

`scripts/synthetic-check.sh`:

```bash
#!/usr/bin/env bash
# Синтетическая проверка витрины по SREDA_SITE_URL. Без адреса — честный пропуск.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${SREDA_SITE_URL:-}" ]; then
    printf '[synthetic] проверка не настроена: SREDA_SITE_URL не задан\n'
    exit 0
fi
exec "$REPO_ROOT/scripts/smoke-static.sh" "$SREDA_SITE_URL"
```

- [ ] **Step 2: Проверить пропуск и реальный адрес**

Run: `env -u SREDA_SITE_URL bash scripts/synthetic-check.sh; echo "exit=$?"`
Expected: `[synthetic] проверка не настроена: SREDA_SITE_URL не задан`, `exit=0`.

Run: локальный тест:

```bash
set -e
TMP=/tmp/opencode/synthetic-site
rm -rf "$TMP" && mkdir -p "$TMP"
printf '<html>Sreda Media marker</html>' > "$TMP/index.html"
printf '<html>404</html>' > "$TMP/404.html"
python3 -m http.server 18082 --directory "$TMP" >/tmp/opencode/synthetic-http.log 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
curl --retry 5 --retry-connrefused --retry-delay 1 -fsS http://127.0.0.1:18082/ >/dev/null
SREDA_SITE_URL=http://127.0.0.1:18082 SREDA_SMOKE_MARKER='Sreda Media marker' bash scripts/synthetic-check.sh
kill $PID 2>/dev/null || true
trap - EXIT
```

Expected: `[smoke] главная=200, отсутствующая=404, маркер=Sreda Media marker`.

- [ ] **Step 3: Рецепт и коммит**

После рецепта `smoke url` добавить:

```
# Синтетическая проверка по SREDA_SITE_URL, не в verify.
synthetic:
    bash scripts/synthetic-check.sh
```

```bash
git add scripts/synthetic-check.sh justfile
git commit -F- <<'MSG'
chore(devops): add gated synthetic check

Скрипт переиспользует smoke-static.sh и работает только при заданном
SREDA_SITE_URL. Без адреса он честно сообщает «проверка не настроена» и
возвращает 0; после Q-1 тот же вызов проверяет 200/404 и маркер контента.
Рецепт just synthetic не входит в verify.

Refs: #9 #14
MSG
```

---

## Task 2: Keyless provenance под флагом

**Files:**
- Create: `.github/workflows/provenance.yml`
- Modify: `docs/DEVOPS-STATUS.md` (пометка о гейте)

- [ ] **Step 1: Workflow**

`.github/workflows/provenance.yml`:

```
name: Provenance (gated)

# Keyless-подпись и SLSA provenance. Выполняется только после ENABLE_PROVENANCE=true
# и явного workflow_dispatch. Не входит в обязательный статус ci.
on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  provenance:
    name: Sign and attest artifact
    if: ${{ vars.ENABLE_PROVENANCE == 'true' }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          persist-credentials: false
      - name: Setup just
        uses: ./.github/actions/setup-just # zizmor: ignore[self-repository]
      - name: Build static artifact
        run: just build-site
      - name: Install cosign
        uses: sigstore/cosign-installer@fb28c2b6339dcd94da6e4cbcbc5e888961f6f8c3 # v3.9.2
      - name: Prepare hash and signature
        run: ./scripts/sign-artifact.sh dist
      - name: Verify hash and signature
        run: ./scripts/verify-artifact.sh dist
      - name: Attest provenance
        uses: actions/attest-build-provenance@e8998f949152b193b063cb0ec769d69d929409be # v2.4.0
        with:
          subject-path: dist/artifact.tar.gz
```

- [ ] **Step 2: Проверить workflow**

Run: `/tmp/opencode/bin/actionlint -color`
Expected: 0 ошибок.

Run: `GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular`
Expected: `No findings to report. Good job!`

Run: `python3 scripts/audit_workflows.py`
Expected: `ok: workflow pins — ... uses, внешние зафиксированы по SHA`.

- [ ] **Step 3: Коммит**

```bash
git add .github/workflows/provenance.yml
git commit -F- <<'MSG'
ci(devops): prepare gated keyless provenance workflow

Добавлен workflow_dispatch-only workflow с guard ENABLE_PROVENANCE=true. Он
собирает витрину, подписывает artifact.tar.gz через cosign keyless, проверяет
его через verify-artifact.sh и создаёт SLSA provenance. Права ограничены
contents: read и id-token: write; workflow вне обязательного статуса ci.
Флаг не выставляется — включение после PR #16, Q-1 и решения по ADR 0006.

Refs: #9 #14
MSG
```

---

## Task 3: Внешняя SLO-панель без авто-провизионинга

**Files:**
- Create: `deploy/observability/grafana-dashboards/gated/slo-external.json`
- Modify: `docs/DEVOPS-STATUS.md` (порядок включения SLO-алертов)

- [ ] **Step 1: Дашборд**

`deploy/observability/grafana-dashboards/gated/slo-external.json`:

```
{
  "uid": "sreda-slo-external",
  "title": "Sreda SLO — external probe",
  "schemaVersion": 39,
  "version": 1,
  "editable": true,
  "tags": ["gated", "external"],
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "External availability (%)",
      "targets": [
        {"refId": "A", "expr": "avg_over_time(probe_success{job=\"sreda-external\"}[30d]) * 100"}
      ],
      "gridPos": {"h": 9, "w": 12, "x": 0, "y": 0}
    },
    {
      "id": 2,
      "type": "timeseries",
      "title": "External probe latency",
      "targets": [
        {"refId": "B", "expr": "probe_duration_seconds{job=\"sreda-external\"}"}
      ],
      "gridPos": {"h": 9, "w": 12, "x": 12, "y": 0}
    }
  ]
}
```

Каталог `gated/` намеренно не попадает в provisioner `dashboards.yml` (его путь `/var/lib/grafana/dashboards` и файлы верхнего уровня не рекурсивны для этого каталога в текущей конфигурации). Дашборд включается вручную после появления независимой точки проверки.

- [ ] **Step 2: Порядок включения алертов в статусной странице**

Добавить в `docs/DEVOPS-STATUS.md` раздел:

```
## Порядок включения SLO-алертов

Включение — отдельный коммит, только после слияния PR #16 и получения адреса Q-1:

1. Заполнить Telegram contact point через env `GRAFANA_TELEGRAM_BOT_TOKEN` и `GRAFANA_TELEGRAM_CHAT_ID`.
2. В `deploy/observability/grafana-provisioning/alerting/rules.yml` заменить `labels.enabled: "false"` на `"true"` только у трёх SLO-правил.
3. Запустить `just check-alerts` и убедиться, что все правила по-прежнему валидны.
4. Применить `deploy/observability/grafana-dashboards/gated/slo-external.json` после настройки внешнего probe.
5. Записать дату включения в этот раздел.

До выполнения этих шагов алерты остаются выключенными, а `just check-alerts`
проверяет именно выключенное состояние.
```

- [ ] **Step 3: Верификация и коммит**

```bash
set -e
python3 -m json.tool deploy/observability/grafana-dashboards/gated/slo-external.json >/dev/null
python3 scripts/check.py
python3 scripts/config_lint.py
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-hardening-after
```

```bash
git add deploy/observability/grafana-dashboards/gated/slo-external.json docs/DEVOPS-STATUS.md
git commit -F- <<'MSG'
docs: prepare external SLO panel and alert activation order

Добавлен дашборд sreda-slo-external в отдельном каталоге gated/, чтобы он не
попал в авто-провизионинг до появления независимой точки проверки. В статусной
странице зафиксирован порядок включения SLO-алертов отдельным коммитом после
PR #16 и Q-1: Telegram через env, смена enabled, just check-alerts и дата.
Ни один флаг и ни одно правило сейчас не включаются.

Refs: #9 #14
MSG
```

---

## Task 4: Итоговая проверка без включения

**Files:** без изменений; только проверки.

- [ ] **Step 1: Статические проверки**

```bash
set -e
bash -n scripts/synthetic-check.sh
python3 -m py_compile scripts/check_branch_policy.py
python3 scripts/check.py
python3 scripts/config_lint.py
/tmp/opencode/bin/actionlint -color
GH_TOKEN=$(gh auth token) uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
python3 scripts/audit_workflows.py
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir /tmp/opencode/mkdocs-hardening-after-final
```

Expected: всё зелёное; `ENABLE_DEPLOY`, `ENABLE_DOCS_PAGES`, `ENABLE_PROVENANCE` не выставлены; `SREDA_SITE_URL` не задан; правила `enabled: "false"`.

- [ ] **Step 2: Подтверждение, что ничего не включено**

```bash
grep -R 'ENABLE_DEPLOY\|ENABLE_DOCS_PAGES\|ENABLE_PROVENANCE' .github/workflows | grep 'true' || echo 'gates: all disabled by default'
grep -c 'enabled: "true"' deploy/observability/grafana-provisioning/alerting/rules.yml || echo 'alerts: none enabled'
git status --short
```

Expected: `gates: all disabled by default`, `alerts: none enabled`, чистое рабочее дерево.
