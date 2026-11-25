#!/usr/bin/env python3
"""Требует, чтобы внешние uses: были зафиксированы по 40-символьному SHA."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
SHA = re.compile(r"@[0-9a-f]{40}$", re.I)


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    bad = []
    count = 0
    # Оба расширения, без повторной обработки одного файла.
    workflows = {
        wf
        for pattern in ("*.yml", "*.yaml")
        for wf in (ROOT / ".github/workflows").glob(pattern)
    }
    for wf in sorted(workflows):
        for lineno, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if not match:
                continue
            value = match.group(1).strip("\"'")
            count += 1
            if value.startswith("./"):
                continue
            if value.startswith("${{"):
                continue  # динамическая ссылка, не опечатка
            if not SHA.search(value):
                bad.append(f"{wf.relative_to(ROOT)}:{lineno}: uses {value} без SHA-пина")
    if bad:
        for line in bad[:50]:
            print(line)
        fail(f"workflow pins: {len(bad)} ошибок")
    print(f"ok: workflow pins — {count} uses, внешние зафиксированы по SHA")


if __name__ == "__main__":
    main()
