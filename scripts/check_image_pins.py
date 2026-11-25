#!/usr/bin/env python3
"""Read-only проверка: образы в deploy зафиксированы по тегу или digest."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
IMAGE = re.compile(r"^\s*image:\s*([^\s#]+)")
GLITCHTIP_EXEMPT = "${GLITCHTIP_IMAGE:-glitchtip/glitchtip:latest}"


def fail_all(errors):
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)


def main():
    base = ROOT / "deploy"
    if not base.is_dir():
        fail_all(["нет каталога deploy"])
    errors = []
    checked = 0
    for path in sorted(base.rglob("*.yml")):
        rel = path.relative_to(ROOT)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = IMAGE.match(line)
            if not match:
                continue
            checked += 1
            image = match.group(1).strip("\"'")
            if image == GLITCHTIP_EXEMPT:
                continue
            if "@sha256:" in image:
                continue
            if ":" not in image or image.rsplit(":", 1)[1] == "latest":
                errors.append(f"{rel}:{number}: образ без фиксированной версии: {image}")
    if errors:
        fail_all(errors)
    print(f"ok: image pins — {checked} образов зафиксированы")


if __name__ == "__main__":
    main()
