#!/usr/bin/env python3
"""Проверка хостовых шаблонов как кода. Только чтение и временные копии.

Запуск: python3 scripts/check_host_config.py [root]
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    "deploy/host/Caddyfile.template",
    "deploy/host/docker-daemon.json.template",
    "deploy/host/journald-vacuum.service",
    "deploy/host/journald-vacuum.timer",
)


def fail(msg: str) -> None:
    raise SystemExit(f"FAIL: {msg}")


def skip(msg: str) -> None:
    print(f"skip: {msg}")


def check_files(base: Path) -> None:
    for rel in FILES:
        if not (base / rel).is_file():
            fail(f"нет файла {rel}")


def check_caddy(base: Path) -> str:
    text = (base / FILES[0]).read_text(encoding="utf-8")
    if "{{SREDA_SITE_URL}}" not in text:
        fail("Caddyfile.template: нужен плейсхолдер {{SREDA_SITE_URL}}")
    if "sreda.sielom.ru" in text or "://" in text:
        fail("Caddyfile.template: не храним реальный адрес или схему в шаблоне")
    for needle in ("root * /srv/sreda/current", "file_server", "404.html", "format json"):
        if needle not in text:
            fail(f"Caddyfile.template: нет обязательной строки {needle!r}")
    return text.replace("{{SREDA_SITE_URL}}", "https://sreda.invalid")


def check_daemon(base: Path) -> None:
    raw = (base / FILES[1]).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"docker-daemon.json.template: неверный JSON: {exc}")
    if data.get("log-driver") != "json-file":
        fail("docker-daemon.json.template: log-driver должен быть json-file")
    opts = data.get("log-opts") or {}
    if opts.get("max-size") != "10m" or opts.get("max-file") != "3":
        fail("docker-daemon.json.template: нужны log-opts max-size=10m, max-file=3")


def check_units(base: Path) -> None:
    service = (base / FILES[2]).read_text(encoding="utf-8")
    timer = (base / FILES[3]).read_text(encoding="utf-8")
    if "[Unit]" not in service or "[Service]" not in service:
        fail("journald-vacuum.service: нужны секции [Unit] и [Service]")
    if "--vacuum-size=500M" not in service or "--vacuum-time=7d" not in service:
        fail("journald-vacuum.service: нужны параметры вакуума 500M и 7d")
    for needle in ("[Unit]", "[Timer]", "OnCalendar=weekly", "Persistent=true", "Unit=journald-vacuum.service", "WantedBy=timers.target"):
        if needle not in timer:
            fail(f"journald-vacuum.timer: нет обязательной строки {needle!r}")


def check_tools(base: Path, caddy_text: str) -> None:
    with tempfile.TemporaryDirectory(prefix="sreda-host-check-") as tmp:
        tmpdir = Path(tmp)
        caddy_file = tmpdir / "Caddyfile"
        caddy_file.write_text(caddy_text, encoding="utf-8")
        if shutil.which("caddy"):
            proc = subprocess.run(["caddy", "validate", "--config", str(caddy_file)], capture_output=True, text=True)
            if proc.returncode != 0:
                fail(f"caddy validate: {proc.stderr.strip() or proc.stdout.strip()}")
        else:
            skip("caddy не установлен: caddy validate не запускался")
        if shutil.which("systemd-analyze"):
            units = [tmpdir / Path(rel).name for rel in FILES[2:]]
            for src, dst in zip(FILES[2:], units):
                shutil.copy2(base / src, dst)
            proc = subprocess.run(["systemd-analyze", "verify", *map(str, units)], capture_output=True, text=True)
            if proc.returncode != 0:
                fail(f"systemd-analyze verify: {proc.stderr.strip() or proc.stdout.strip()}")
        else:
            skip("systemd-analyze не найден: проверка юнитов не запускалась")


def main() -> None:
    base = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
    check_files(base)
    caddy_text = check_caddy(base)
    check_daemon(base)
    check_units(base)
    check_tools(base, caddy_text)
    print("ok: host config — Caddy, docker daemon и journald vacuum подготовлены")


if __name__ == "__main__":
    main()
