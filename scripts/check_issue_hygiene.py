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
