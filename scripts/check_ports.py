#!/usr/bin/env python3
"""Read-only проверка карты портов compose-файлов (ADR 0006)."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
BIND = re.compile(r'^\s*-\s*"(?:([^:]+):)?(\d+):(\d+)"\s*$')
EXPECTED = {
    "dev/postgres.yml": {55432},
    "dev/docker-compose.yml": {13000, 13100, 13345},
    "observability/docker-compose.yml": {3000, 3100, 12345, 9090, 9100, 9115, 5432, 8000},
    "uptime-kuma/docker-compose.yml": {3001},
}


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def main():
    errors = []
    seen = set()
    for rel, expected in EXPECTED.items():
        path = ROOT / "deploy" / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{rel}: не удалось прочитать: {exc}")
            continue
        ports = []
        for line in text.splitlines():
            match = BIND.match(line)
            if not match:
                continue
            host, published, container = match.groups()
            if host != "127.0.0.1":
                errors.append(f"{rel}: порт {published} не привязан к 127.0.0.1")
            port = int(published)
            ports.append(port)
        if len(ports) != len(set(ports)):
            errors.append(f"{rel}: дублирование host-портов")
        actual = set(ports)
        if actual != expected:
            errors.append(
                f"{rel}: ожидаемые порты {sorted(expected)}, фактические {sorted(actual)}"
            )
        seen.update(actual)
    if errors:
        fail_all(errors)
    print(f"ok: ports — {len(seen)} уникальных портов, все на 127.0.0.1")


if __name__ == "__main__":
    main()
