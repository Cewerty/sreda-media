#!/usr/bin/env python3
"""Read-only проверка контракта корневого артефакта витрины."""
from pathlib import Path
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
ARTIFACT = ROOT / "dist"
errors: list[str] = []


def check_required(name: str) -> None:
    path = ARTIFACT / name
    if not path.is_file():
        if name == "404.html":
            errors.append("dist/404.html отсутствует: issue #5, страница 404 в зоне фронтенда")
        else:
            errors.append(f"dist/{name} отсутствует")
        return
    if path.stat().st_size == 0:
        errors.append(f"dist/{name} пустой")


if not ARTIFACT.is_dir():
    errors.append("нет каталога dist: сначала запустите just stage-site")
else:
    check_required("index.html")
    check_required("404.html")

if errors:
    for message in errors:
        print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)

print("ok: artifact contract — dist/index.html и dist/404.html на месте")
