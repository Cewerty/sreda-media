#!/usr/bin/env python3
"""Read-only сверка плейсхолдеров окружения с шаблонами."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".ruff_cache", ".venv"}
PLACEHOLDER = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
ASSIGN = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", re.M)
TOKEN = re.compile(r"\b([A-Z][A-Z0-9_]{3,})\b")
SHELL_LOCAL = {
    "PREFIX", "RETENTION_DAYS", "TS", "SQL_FILE", "GRAFANA_FILE", "SREDA_SITE_URL",
}
SCAN_DIRS = ("deploy", ".github", "scripts")
SCAN_FILES = ("justfile",)
ENV_FILES = ("deploy/observability/.env.example", "apps/cms-api/.env.example")


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def read(rel):
    try:
        return (ROOT / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail_all([f"{rel}: не удалось прочитать: {exc}"])


def known_names():
    names = set()
    for rel in ENV_FILES:
        names.update(ASSIGN.findall(read(rel)))
    names.update(TOKEN.findall(read("docs/SECRET-ROTATION.md")))
    names.update(SHELL_LOCAL)
    return names


def source_files():
    found = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if not base.is_dir():
            fail_all([f"нет каталога: {rel}"])
        for path in base.rglob("*"):
            if path.is_file() and not SKIP_DIRS.intersection(path.parts):
                if path.suffix != ".pyc":
                    found.append(path)
    for rel in SCAN_FILES:
        path = ROOT / rel
        if path.is_file():
            found.append(path)
    return found


def main():
    known = known_names()
    found = {}
    for path in source_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for name in PLACEHOLDER.findall(text):
            found.setdefault(name, str(path.relative_to(ROOT)))
    unknown = sorted(set(found) - known)
    if unknown:
        fail_all([f"${{{name}}}: нет в .env.example или документации ({found[name]})" for name in unknown])
    print(f"ok: env contract — {len(found)} плейсхолдеров, все объявлены")


if __name__ == "__main__":
    main()
