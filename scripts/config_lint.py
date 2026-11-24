#!/usr/bin/env python3
"""Валидация конфигурационных файлов монорепозитория (stdlib, без зависимостей).

Проверяет JSON и TOML, обязательные файлы конфигурации workspace и базовую
структуру workflow-файлов. Полный разбор YAML делают actionlint и zizmor
через `just workflows-lint`.
"""

import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".pnpm-store", "dist", "build"}
REQUIRED = (
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
    "pnpm-lock.yaml",
    ".github/CODEOWNERS",
)


def files(ext: str):
    for path in ROOT.rglob(f"*{ext}"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def main() -> int:
    errors = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"отсутствует обязательный файл: {name}")

    json_count = 0
    for path in files(".json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"JSON {path.relative_to(ROOT)}: {exc}")
        json_count += 1

    toml_count = 0
    for path in files(".toml"):
        try:
            with path.open("rb") as fh:
                tomllib.load(fh)
        except Exception as exc:
            errors.append(f"TOML {path.relative_to(ROOT)}: {exc}")
        toml_count += 1

    workflows = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        errors.append("нет workflow-файлов в .github/workflows")
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        for key in ("name:", "on:", "jobs:"):
            if key not in text:
                errors.append(f"{path.relative_to(ROOT)}: нет обязательного ключа {key}")

    if errors:
        for line in errors:
            print(f"FAIL: {line}")
        return 1

    print(f"ok: JSON {json_count}, TOML {toml_count}, workflow {len(workflows)} — конфигурация валидна")
    return 0


if __name__ == "__main__":
    sys.exit(main())
