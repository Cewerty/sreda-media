#!/usr/bin/env python3
"""Репетиция alarms: статическая проверка правил + тестовая запись в Loki.

Запуск: python3 scripts/alert-drill.py
Переменные: LOKI_URL (по умолчанию http://127.0.0.1:3100).

ВАЖНО: если локальный Loki не поднят, скрипт честно сообщает о пропуске
инъекции, но статическая проверка правил всё равно обязательна. Скрипт не
изменяет provisioning и не включает отключённые алерты.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOKI_URL = __import__("os").environ.get("LOKI_URL", "http://127.0.0.1:3100").rstrip("/")
LINE = "alert_drill backup_failed synthetic event for provisioning check"


def log(msg: str) -> None:
    print(f"[alert-drill] {msg}", flush=True)


def fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(f"[alert-drill] ОШИБКА: {msg}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def request(url: str, data: bytes | None = None, headers: dict[str, str] | None = None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


def main() -> int:
    static = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_alert_rules.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if static.returncode != 0:
        print(static.stdout, end="")
        print(static.stderr, end="", file=sys.stderr)
        fail("статическая проверка provisioning не прошла")
    log(static.stdout.strip())

    try:
        code, _ = request(f"{LOKI_URL}/ready")
        log(f"Loki /ready → {code}")
    except (urllib.error.URLError, OSError) as exc:
        log(f"Loki недоступен ({exc}); инъекция пропущена, статическая проверка пройдена")
        return 0

    payload = {
        "streams": [
            {
                "stream": {"job": "alert-drill", "component": "backup", "environment": "development"},
                "values": [[str(time.time_ns()), LINE]],
            }
        ]
    }
    try:
        code, body = request(
            f"{LOKI_URL}/loki/api/v1/push",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if code not in (200, 204):
            fail(f"запись в Loki вернула {code}: {body[:200]}")
        log(f"тестовое событие отправлено в Loki → {code}")
    except (urllib.error.URLError, OSError) as exc:
        fail(f"не удалось записать событие в Loki: {exc}")

    query = '{job="alert-drill"} |= "backup_failed"'
    url = f"{LOKI_URL}/loki/api/v1/query?{urllib.parse.urlencode({'query': query, 'limit': 10})}"
    try:
        code, body = request(url)
    except (urllib.error.URLError, OSError) as exc:
        fail(f"не удалось запросить Loki: {exc}")
    try:
        result = json.loads(body).get("data", {}).get("result", [])
    except json.JSONDecodeError as exc:
        fail(f"некорректный ответ Loki: {exc}")
    if not result:
        fail("тестовое событие не найдено в Loki")
    log("событие найдено в Loki: канал сбора работает (алерты остаются отключёнными)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
