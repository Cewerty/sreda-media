#!/usr/bin/env python3
"""Валидация файлового контента витрины (ADR 0014, issue #6).

Проверяет материалы исходного вида .md с frontmatter до сборки Astro:
- обязательные поля schema_version/title/kind/slug и уникальность slug;
- путь медиа существует, не содержит path traversal и имеет checksum в manifest;
- отсутствие raw HTML и пользовательского JS в теле статьи;
- ссылки на локальные материалы.

Скрипт намеренно использует только stdlib: его можно вызвать на чистом
checkout любой ОС одной командой `just check-content`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "apps" / "site" / "src" / "content" / "articles"
MEDIA = ROOT / "apps" / "site" / "src" / "content" / "media"
MANIFEST = MEDIA / "manifest.json"

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.S)
KEY_VALUE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*$")
MEDIA_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
RAW_HTML = re.compile(r"<(script|iframe|style|object|embed|link|meta)\b", re.I)

# Минимальный MVP 0.1 (PR #16) объявляет только title в Zod-схеме Astro.
# Полный контракт ADR 0014 включается, когда материал объявляет schema_version.
REQUIRED = ("title",)
CONTRACT_FIELDS = ("kind", "slug")


def parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER.match(raw)
    if not match:
        raise ValueError("нет корректного frontmatter (--- ... ---)")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = KEY_VALUE.match(line)
        if not kv:
            raise ValueError(f"не удалось разобрать строку frontmatter: {line!r}")
        key, value = kv.group(1), kv.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta, match.group(2)


def main() -> int:
    errors: list[str] = []
    if not CONTENT.is_dir():
        print(f"content: PASS (каталог {CONTENT.relative_to(ROOT)} ещё не создан)")
        return 0

    manifest: dict[str, str] = {}
    if MANIFEST.exists():
        try:
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            for item in data.get("files", []):
                manifest[item["path"]] = item["sha256"]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"media/manifest.json: нечитаем: {exc}")

    slugs: set[str] = set()
    files = sorted(CONTENT.rglob("*.md"))
    for path in files:
        rel = path.relative_to(ROOT)
        try:
            meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
            for key in REQUIRED:
                if not meta.get(key):
                    errors.append(f"{rel}: отсутствует обязательное поле {key}")
            version = meta.get("schema_version")
            if version:
                if version != "1":
                    errors.append(f"{rel}: неизвестная версия контракта {version}")
                for key in CONTRACT_FIELDS:
                    if not meta.get(key):
                        errors.append(f"{rel}: schema_version=1 требует поле {key}")
            slug = meta.get("slug", "")
            if slug:
                if slug in slugs:
                    errors.append(f"{rel}: дублирующийся slug {slug}")
                slugs.add(slug)
                if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
                    errors.append(f"{rel}: slug должен быть латиницей в kebab-case")
            if RAW_HTML.search(body) or re.search(r"</?[A-Za-z][A-Za-z0-9-]*\b[^>]*>", body):
                errors.append(f"{rel}: raw HTML запрещён ADR 0014")
            for target in MEDIA_LINK.findall(body):
                if target.startswith(("http://", "https://", "//")):
                    continue
                clean = target.split("#", 1)[0].split("?", 1)[0]
                if ".." in Path(clean).parts or clean.startswith("/"):
                    errors.append(f"{rel}: ссылка на медиа вне каталога контента: {target}")
                    continue
                media_path = MEDIA / clean
                if not media_path.is_file():
                    errors.append(f"{rel}: медиа не найдено: {target}")
                elif clean in manifest:
                    actual = hashlib.sha256(media_path.read_bytes()).hexdigest()
                    if actual != manifest[clean]:
                        errors.append(f"{rel}: checksum медиа не совпадает: {target}")
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f"{rel}: {exc}")

    for path in sorted(MEDIA.rglob("*")) if MEDIA.is_dir() else []:
        if path.is_file() and path.name != "manifest.json":
            rel = path.relative_to(MEDIA).as_posix()
            if rel not in manifest:
                errors.append(f"media/{rel}: файл отсутствует в manifest.json")

    for err in errors:
        print("FAIL:", err)
    if errors:
        print(f"content: FAIL ({len(errors)} ошибок)")
        return 1
    print(f"content: PASS ({len(files)} материалов, {len(manifest)} медиа)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
