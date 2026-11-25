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
