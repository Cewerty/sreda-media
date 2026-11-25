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
