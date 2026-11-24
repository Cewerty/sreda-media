#!/usr/bin/env python3
"""Единая проверка соглашений репозитория на чистом checkout.

Запуск: `python3 scripts/check.py` (или `just check`). Без сети, БД, учётных
данных и внешних зависимостей. Проверяет обязательные файлы, имена и статусы
ADR, относительные ссылки Markdown, баланс блоков кода, шаблонные секреты и
формат CODEOWNERS. В CI этот скрипт выполняет job `conventions`; итоговый
обязательный статус публикует job `ci`. Локальный результат совпадает с CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAIL: list[str] = []

REQUIRED = (
    "AGENTS.md",
    "CONTRIBUTING.md",
    "docs/prd.md",
    "docs/architecture.md",
    "docs/roadmap.md",
    ".github/CODEOWNERS",
    "LICENSE",
)

ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
ADR_STATUS = re.compile(r"^## Статус:\s*(.+?)\s*$", re.M)
ADR_TITLE = re.compile(r"^# ADR \d+:", re.M)
ALLOWED_STATUS = {"Accepted", "Proposed", "Superseded", "Draft"}
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".next"}


def fail(message: str) -> None:
    FAIL.append(message)


def ok(message: str) -> None:
    print("ok:", message)


def files() -> list[Path]:
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not SKIP_DIRS.intersection(p.parts)
        and p.stat().st_size < 1_000_000
    ]


def markdown_files() -> list[Path]:
    return sorted(p for p in files() if p.suffix == ".md")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def check_required() -> None:
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(f"нет обязательного файла: {rel}")
    if not FAIL:
        ok(f"обязательные файлы ({len(REQUIRED)}) на месте")


def check_adrs() -> None:
    adr_dir = ROOT / "docs" / "adr"
    names = sorted(p.name for p in adr_dir.glob("*.md")) if adr_dir.is_dir() else []
    if not names:
        fail("нет ADR в docs/adr/")
        return
    bad_names = [n for n in names if not ADR_NAME.match(n)]
    if bad_names:
        fail("ADR с неверным именем: " + ", ".join(bad_names))
    numbers = [int(ADR_NAME.match(n).group(1)) for n in names if ADR_NAME.match(n)]
    if numbers != list(range(1, len(numbers) + 1)):
        fail(f"нумерация ADR не непрерывна: {numbers}")
    for name in names:
        text = read_text(adr_dir / name) or ""
        status = ADR_STATUS.search(text)
        if not status:
            fail(f"{name}: нет поля '## Статус:'")
        elif status.group(1) not in ALLOWED_STATUS:
            fail(f"{name}: неизвестный статус {status.group(1)!r}")
        if not ADR_TITLE.search(text):
            fail(f"{name}: нет заголовка '# ADR N:'")
    ok(f"ADR: {len(names)} файлов, имена, нумерация и статусы корректны")


def check_links() -> None:
    count = 0
    for path in markdown_files():
        text = read_text(path) or ""
        for raw in LINK.findall(text):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            rel = target.split("#", 1)[0]
            if not rel:
                continue
            resolved = (path.parent / rel).resolve()
            if not resolved.exists():
                fail(f"{path.relative_to(ROOT)}: ссылка не существует: {raw}")
            count += 1
    ok(f"относительные ссылки Markdown: {count} проверено")


def check_fences() -> None:
    for path in markdown_files():
        text = read_text(path) or ""
        fences = sum(1 for line in text.splitlines() if line.lstrip().startswith("```"))
        if fences % 2:
            fail(f"{path.relative_to(ROOT)}: нечётное число тройных backtick")
    ok("блоки кода в Markdown сбалансированы")


def _token(prefix: str, length: int) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(prefix) + r"[A-Za-z0-9_-]{%d,}" % length)


# Префиксы собраны из частей, чтобы сам скрипт не срабатывал как ложное срабатывание.
SECRET_PATTERNS = (
    ("GitHub token", _token("gh" + "p_", 30)),
    ("GitHub refresh token", _token("github" + "_pat_", 30)),
    ("API key", _token("sk" + "-", 24)),
    ("AWS key", re.compile(r"(?<![A-Za-z0-9])" + "AK" + "IA" + r"[0-9A-Z]{16}")),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE " + "KEY-----")),
)


def check_secrets() -> None:
    hits: list[str] = []
    for path in files():
        text = read_text(path)
        if text is None:
            continue
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {name}")
    if hits:
        fail("похожие на секреты строки: " + ", ".join(hits))
    else:
        ok("секреты: шаблонных утечек нет")


def check_codeowners() -> None:
    path = ROOT / ".github" / "CODEOWNERS"
    if not path.is_file():
        return
    owner = re.compile(r"@[A-Za-z0-9-]+")
    for line in (read_text(path) or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            fail(f"CODEOWNERS: строка без владельца: {line}")
            continue
        for who in parts[1:]:
            if not owner.fullmatch(who):
                fail(f"CODEOWNERS: некорректный владелец {who!r}")
    ok("CODEOWNERS: формат владельцев корректный")


def main() -> int:
    check_required()
    check_adrs()
    check_links()
    check_fences()
    check_secrets()
    check_codeowners()
    if FAIL:
        print("\n".join("FAIL: " + m for m in FAIL), file=sys.stderr)
        return 1
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
