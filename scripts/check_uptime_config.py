#!/usr/bin/env python3
"""Проверка конфигурации Uptime Kuma как кода (issue #14, этап 0.1)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "deploy/uptime-kuma/monitors.json"

def fail(msg):
    raise SystemExit(f"FAIL: {msg}")

def main():
    raw = CONF.read_text(encoding="utf-8")
    data = json.loads(raw)
    if "${SREDA_SITE_URL}" not in raw:
        fail("URL мониторов должен использовать ${SREDA_SITE_URL}")
    monitors = data.get("monitors", [])
    if len(monitors) < 2:
        fail("нужны минимум два монитора: главная и 404")
    default_interval = data.get("interval_seconds")
    if not isinstance(default_interval, int) or default_interval < 30:
        fail("общий interval_seconds должен быть >=30")
    statuses = {}
    for m in monitors:
        if m.get("type") != "http":
            fail("ожидается http-монитор")
        interval = m.get("interval_seconds", default_interval)
        if not isinstance(interval, int) or interval < 30:
            fail(f"слишком маленький интервал: {m.get('name')}")
        statuses[m.get("name")] = m.get("expected_status")
    if statuses.get("sreda-main") != 200:
        fail("sreda-main должен ожидать 200")
    if statuses.get("sreda-404") != 404:
        fail("sreda-404 должен ожидать 404")
    if not re.search(r'"notification"\s*:\s*"telegram', raw):
        fail("нужно Telegram-уведомление")
    print("ok: Uptime Kuma — 2 монитора (200/404), интервал >=30с, Telegram, URL через env")

if __name__ == "__main__":
    main()
