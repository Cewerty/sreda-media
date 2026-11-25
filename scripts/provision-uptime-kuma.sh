#!/usr/bin/env bash
# Декларативное описание мониторов Uptime Kuma (issue #14). НЕ запускается в CI
# и не меняет сервисы: требуется реальный адрес сайта и токен API.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFS="$REPO_ROOT/deploy/uptime-kuma/monitors.json"
URL="${UPTIME_KUMA_URL:-}"
TOKEN="${UPTIME_KUMA_TOKEN:-}"
DRY_RUN="${DRY_RUN:-1}"
[ -f "$DEFS" ] || { echo "[kuma] нет $DEFS" >&2; exit 1; }
python3 -m json.tool "$DEFS" >/dev/null
echo "[kuma] декларация корректна: $DEFS"
if [ "$DRY_RUN" = "1" ]; then echo "[kuma] DRY_RUN: запросы к API не отправляются"; exit 0; fi
[ -n "$URL" ] && [ -n "$TOKEN" ] || { echo "[kuma] нужны UPTIME_KUMA_URL и UPTIME_KUMA_TOKEN" >&2; exit 1; }
curl -fsS -H "Authorization: Bearer $TOKEN" "$URL/api/v1/monitor/list" >/dev/null
echo "[kuma] API доступен; применение мониторов делается вручную по monitors.json"
