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
