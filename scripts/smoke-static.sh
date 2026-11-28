#!/usr/bin/env bash
# Smoke-проверка статической витрины после выкладки (issue #7, ADR 0015).
#
#   scripts/smoke-static.sh https://sreda.sielom.ru
#
# Проверяет главную (200), заведомо несуществующую страницу (404) и, если задан
# SREDA_SMOKE_MARKER, наличие маркера контента на главной. Только чтение.
set -euo pipefail

log() { printf '[smoke] %s\n' "$*" >&2; }
fail() { printf '[smoke] FAIL: %s\n' "$*" >&2; exit 1; }

base=${1:?usage: smoke-static.sh <base-url>}
base=${base%/}
marker=${SREDA_SMOKE_MARKER:-}
missing=${SREDA_SMOKE_MISSING_PATH:-/__sreda-smoke-missing__}
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

main_code=$(curl -sS --connect-timeout 5 --max-time 10 \
    -o "$tmp" -w '%{http_code}' "$base/" || true)
[ "$main_code" = "200" ] || fail "главная отдаёт $main_code, ожидался 200"
if [ -n "$marker" ]; then
    grep -qF "$marker" "$tmp" || fail "на главной нет маркера: $marker"
fi

missing_code=$(curl -sS --connect-timeout 5 --max-time 10 \
    -o /dev/null -w '%{http_code}' "$base$missing" || true)
[ "$missing_code" = "404" ] || fail "несуществующая страница отдаёт $missing_code, ожидался 404"

log "главная=$main_code, отсутствующая=$missing_code, маркер=${marker:-не проверялся}"
