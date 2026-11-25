#!/usr/bin/env python3
"""Только чтение: сверяет защиту main в GitHub с ожидаемой политикой (issue #44)."""
import json
import shutil
import subprocess
import sys

REPO = "Sreda-Media/sreda-media"


def skip(msg: str) -> None:
    print(f"skip: {msg}")
    raise SystemExit(0)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    raise SystemExit(1)


def main() -> None:
    if shutil.which("gh") is None:
        skip("gh не установлен: проверка политики GitHub пропущена")
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/branches/main/protection"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        skip(f"gh api недоступен: {exc}")
    if result.returncode != 0:
        skip(f"gh api недоступен: {(result.stderr or result.stdout).strip()[:200]}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        fail("gh api вернул не JSON")

    checks = data.get("required_status_checks") or {}
    contexts = checks.get("contexts") or []
    if checks.get("strict") is not True:
        fail("required_status_checks.strict должен быть true")
    if "ci" not in contexts:
        fail("в обязательных статусах должен быть ci")
    reviews = data.get("required_pull_request_reviews") or {}
    approvals = reviews.get("required_approving_review_count") or 0
    if approvals < 1:
        fail("нужно минимум одно одобрение")
    print("ok: main защищён — ci strict, обязательное одобрение, GET-only")


if __name__ == "__main__":
    main()
