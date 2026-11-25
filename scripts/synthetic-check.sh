#!/usr/bin/env bash
# Синтетическая проверка витрины по SREDA_SITE_URL. Без адреса — честный пропуск.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "${SREDA_SITE_URL:-}" ]; then
    printf '[synthetic] проверка не настроена: SREDA_SITE_URL не задан\n'
    exit 0
fi
exec "$REPO_ROOT/scripts/smoke-static.sh" "$SREDA_SITE_URL"
