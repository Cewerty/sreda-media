#!/usr/bin/env python3
"""Проверить JSONL-примеры логов по ADR 0005 и контракту CMS."""

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples" / "logs"
CMS_EXAMPLE = EXAMPLES / "cms-request-finished.jsonl"
REQUIRED = ("event", "component", "operation", "outcome", "timestamp", "environment", "release")
EVENT_RE = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?")
LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
SENSITIVE = (
    "token", "password", "secret", "authorization", "cookie", "dsn",
    "telegram_id", "username", "email", "phone", "api_key", "apikey",
)


def sensitive_keys(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in key.lower() for word in SENSITIVE):
                yield key
            yield from sensitive_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from sensitive_keys(item)


def check_record(record, *, cms):
    for field in REQUIRED:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            yield f"{field}: требуется непустая строка"

    event = record.get("event")
    if isinstance(event, str) and event and not EVENT_RE.fullmatch(event):
        yield "event: ожидается стабильное имя события"

    timestamp = record.get("timestamp")
    if isinstance(timestamp, str) and timestamp:
        try:
            parsed = datetime.fromisoformat(timestamp)
        except ValueError:
            yield "timestamp: ожидается время ISO 8601"
        else:
            if parsed.tzinfo is None or (cms and not timestamp.endswith("Z")):
                yield "timestamp: ожидается UTC с Z" if cms else "timestamp: требуется часовой пояс"

    level = record.get("level")
    if level is not None and (not isinstance(level, str) or level not in LEVELS):
        yield "level: неизвестный уровень"

    for key in sensitive_keys(record):
        yield f"{key}: поле может содержать персональные данные или секрет"

    if cms:
        yield from check_cms_record(record)


def check_cms_record(record):
    for field, expected in (
        ("event", "request_finished"),
        ("component", "cms-api"),
        ("operation", "http_request"),
    ):
        if record.get(field) != expected:
            yield f"{field}: ожидается {expected}"

    correlation_id = record.get("correlation_id")
    try:
        is_uuid4 = isinstance(correlation_id, str) and UUID(correlation_id).version == 4
    except ValueError:
        is_uuid4 = False
    if not is_uuid4:
        yield "correlation_id: ожидается UUIDv4"

    if type(record.get("status_code")) is not int:
        yield "status_code: ожидается целое число"

    elapsed = record.get("elapsed_ms")
    if type(elapsed) is float:
        valid_elapsed = math.isfinite(elapsed) and elapsed >= 0
    else:
        valid_elapsed = type(elapsed) is int and elapsed >= 0
    if not valid_elapsed:
        yield "elapsed_ms: ожидается конечное неотрицательное число"


def reject_constant(_value):
    raise ValueError("некорректная JSON-константа")


def main():
    errors = []
    checked = 0
    for path in sorted({CMS_EXAMPLE, *EXAMPLES.glob("*.jsonl")}):
        name = path.relative_to(ROOT)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            errors.append(f"{name}: требуется доступный JSONL-файл в UTF-8")
            continue

        if path == CMS_EXAMPLE and not any(line.strip() for line in lines):
            errors.append(f"{name}: требуется хотя бы одна запись")
        for lineno, line in enumerate(lines, 1):
            if not line.strip():
                continue
            checked += 1
            where = f"{name}:{lineno}"
            try:
                record = json.loads(line, parse_constant=reject_constant)
            except ValueError:
                errors.append(f"{where}: некорректный JSON")
                continue
            if not isinstance(record, dict):
                errors.append(f"{where}: ожидался JSON-объект")
                continue
            errors.extend(f"{where}: {error}" for error in check_record(record, cms=path == CMS_EXAMPLE))

    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"ok: проверено записей JSONL: {checked}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
