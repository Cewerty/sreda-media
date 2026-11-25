#!/usr/bin/env bash
# Нормализация артефакта Astro: apps/site/dist -> корневой dist.
# Не собирает сайт, не подписывает, не выкладывает и не трогает /srv.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SRC="apps/site/dist"
DST="dist"

fail() { printf '[stage-site] ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ -d "$SRC" ] || fail "нет каталога $SRC: сначала запустите just build-site"
[ -f "$SRC/index.html" ] || fail "в $SRC нет index.html"

if [ -L "$DST" ]; then
    fail "$DST — симлинк, удаление опасно"
fi

rm -rf "$DST"
mkdir -p "$DST"
cp -a "$SRC/." "$DST/"

count=$(find "$DST" -type f | wc -l)
printf '[stage-site] готово: %s -> %s (%s файлов)\n' "$SRC" "$DST" "$count"
