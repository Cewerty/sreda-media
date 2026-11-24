#!/usr/bin/env python3
"""Проверка контракта структурированных логов из ADR 0005 (stdlib, без зависимостей).

Приложение пишет JSON в stdout; учебный пример лежит в docs/examples/logs/.
Скрипт ищет все *.jsonl в репозитории и проверяет обязательные поля, формат
времени, стабильные имена событий и отсутствие PII/секретов в полях.

Использование: python3 scripts/check_log_schema.py
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".pnpm-store", "dist", "build", "deploy"}
REQUIRED = ("event", "component", "operation", "outcome", "timestamp", "environment", "release")
EVENT_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$")
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
SENSITIVE = (
    "token", "password", "secret", "authorization", "cookie", "dsn",
    "telegram_id", "username", "email", "phone", "api_key", "apikey",
)


def jsonl_files():
    for path in ROOT.rglob("*.jsonl"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def sensitive_keys(value, prefix=""):
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            full = f"{prefix}.{key}" if prefix else str(key)
            if any(word in str(key).lower() for word in SENSITIVE):
                found.append(full)
            found.extend(sensitive_keys(item, full))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(sensitive_keys(item, f"{prefix}[{index}]"))
    return found


def main():
    errors = []
    checked = 0
    events = 0

    for path in sorted(jsonl_files()):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            checked += 1
            where = f"{path.relative_to(ROOT)}:{lineno}"
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{where}: некорректный JSON: {exc.msg}")
                continue
            if not isinstance(record, dict):
                errors.append(f"{where}: ожидался JSON-объект")
                continue

            for field in REQUIRED:
                value = record.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{where}: обязательное поле {field!r} отсутствует или пустое")

            event = record.get("event")
            if isinstance(event, str) and event and not EVENT_RE.match(event):
                errors.append(f"{where}: нестабильное имя события {event!r}")

            timestamp = record.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                try:
                    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    errors.append(f"{where}: timestamp не ISO 8601: {timestamp!r}")
                else:
                    if parsed.tzinfo is None:
                        errors.append(f"{where}: timestamp без часового пояса: {timestamp!r}")

            level = record.get("level")
            if level is not None and level not in LEVELS:
                errors.append(f"{where}: неизвестный level {level!r}")

            leaks = sensitive_keys(record.get("payload", {}))
            if leaks:
                errors.append(f"{where}: потенциальные PII/секреты в payload: {', '.join(leaks)}")
            events += 1

    if errors:
        for line in errors:
            print(f"FAIL: {line}")
        return 1

    print(f"ok: JSONL {checked}, событий {events} — контракт ADR 0005 соблюдён")
    return 0


if __name__ == "__main__":
    sys.exit(main())
