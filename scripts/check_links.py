#!/usr/bin/env python3
"""Лёгкая ежедневная проверка относительных ссылок в docs/ (не заменяет check.py)."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
PAT = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
bad = []
for md in sorted(DOCS.rglob("*.md")):
    text = md.read_text(encoding="utf-8", errors="replace")
    for target in PAT.findall(text):
        if not target or target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        candidate = (md.parent / clean).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            bad.append(f"{md.relative_to(ROOT)}: ссылка вне репозитория: {target}")
        if not candidate.exists():
            bad.append(f"{md.relative_to(ROOT)}: нет файла: {target}")
if bad:
    print("FAIL: link checker")
    for line in bad[:50]:
        print(" ", line)
    sys.exit(1)
print("ok: relative links in docs/ valid")
