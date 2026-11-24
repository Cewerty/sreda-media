#!/usr/bin/env python3
"""Сверяет just-рецепты и scripts/* из bash-блоков docs/*.md с репозиторием."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FENCE = re.compile(r"```(?:bash|sh)\s*\n(.*?)```", re.S | re.I)
JUST = re.compile(r"(?<![\w-])just\s+([A-Za-z0-9_-]+)")
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
        # Планы описывают ещё не созданные файлы и рецепты — не runbook.
        if "superpowers/plans" in doc.relative_to(ROOT).as_posix():
            continue
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
