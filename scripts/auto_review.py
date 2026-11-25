#!/usr/bin/env python3
"""Автоматический запрос ревьюеров по CODEOWNERS (issue #26).

Работает через GitHub REST: читает изменённые файлы PR, выбирает владельцев
по правилам CODEOWNERS (последнее совпадение побеждает, как в GitHub),
исключает автора и уже запрошенных ревьюеров, затем запрашивает остальных.

Окружение: GITHUB_TOKEN, GITHUB_REPOSITORY, PR_NUMBER.
Режим проверки без изменений: --dry-run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
UA = "sreda-auto-review/1.0"


def _request(path: str, token: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": UA,
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None


def parse_codeowners(path: Path) -> list[tuple[str, list[str]]]:
    rules: list[tuple[str, list[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        owners = [p.lstrip("@") for p in parts[1:] if p.startswith("@")]
        if owners:
            rules.append((parts[0], owners))
    return rules


def matches(pattern: str, file_path: str) -> bool:
    pat = pattern.strip()
    if pat == "*":
        return True
    if pat.startswith("/"):
        pat = pat[1:]
    if pat.endswith("/**"):
        base = pat[:-3].rstrip("/")
        return file_path == base or file_path.startswith(base + "/")
    if pat.endswith("/"):
        base = pat.rstrip("/")
        return file_path == base or file_path.startswith(base + "/")
    return file_path == pat or file_path.startswith(pat + "/")


def changed_files(repo: str, number: int, token: str) -> list[str]:
    files: list[str] = []
    page = 1
    while True:
        batch = _request(
            f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}", token
        )
        if not isinstance(batch, list) or not batch:
            break
        files.extend(item["filename"] for item in batch if "filename" in item)
        if len(batch) < 100:
            break
        page += 1
    return files


def select_owners(
    files: list[str],
    rules: list[tuple[str, list[str]]],
    skip: set[str],
) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()
    for file_path in files:
        matched: list[str] = []
        for pattern, owners in rules:
            if matches(pattern, file_path):
                matched = owners  # GitHub CODEOWNERS: последнее совпадение побеждает
        for owner in matched:
            key = owner.lower()
            if key in skip or key.endswith("[bot]") or key in seen:
                continue
            seen.add(key)
            selected.append(owner)
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="только показать выбор")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    raw_number = os.environ.get("PR_NUMBER")
    if not token or not repo or not raw_number:
        print("ERROR: нужны GITHUB_TOKEN, GITHUB_REPOSITORY и PR_NUMBER", file=sys.stderr)
        return 2
    try:
        number = int(raw_number)
    except ValueError:
        print("ERROR: PR_NUMBER должен быть числом", file=sys.stderr)
        return 2

    codeowners = Path(".github/CODEOWNERS")
    if not codeowners.is_file():
        print("ERROR: нет .github/CODEOWNERS", file=sys.stderr)
        return 2

    pr = _request(f"/repos/{repo}/pulls/{number}", token)
    author = str(pr.get("user", {}).get("login", "")).lower()
    already = {
        str(r.get("login", "")).lower()
        for r in pr.get("requested_reviewers", [])
        if r.get("login")
    }
    skip = already | ({author} if author else set())

    files = changed_files(repo, number, token)
    owners = select_owners(files, parse_codeowners(codeowners), skip)

    if not owners:
        print(f"PR #{number}: ревьюеров по CODEOWNERS запрашивать некого")
        return 0
    if args.dry_run:
        print(f"dry-run: PR #{number}, изменённых файлов {len(files)}, запросил бы: {', '.join(owners)}")
        return 0

    endpoint = f"/repos/{repo}/pulls/{number}/requested_reviewers"
    try:
        _request(endpoint, token, method="POST", payload={"reviewers": owners})
        print(f"PR #{number}: запрошено ревью: {', '.join(owners)}")
    except urllib.error.HTTPError as exc:
        if exc.code != 422:
            raise
        print("пакетный запрос отклонён (422), повторяем по одному")
        for owner in owners:
            try:
                _request(endpoint, token, method="POST", payload={"reviewers": [owner]})
                print(f"PR #{number}: запрошено ревью: {owner}")
            except urllib.error.HTTPError as single_exc:
                print(f"PR #{number}: пропущен {owner} (HTTP {single_exc.code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
