#!/usr/bin/env bash
# Локальная проверка поднятого контура наблюдаемости (issue #14, 0.2).
# Ничего не запускает и не перезапускает: только читает docker compose ps и HTTP.
# Переменные: OBS_COMPOSE_FILE, LOKI_URL, GRAFANA_URL, ALLOY_URL, DRY_RUN=1.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# По умолчанию проверяем локальный dev-стек с высокими портами.
COMPOSE_FILE="${OBS_COMPOSE_FILE:-$REPO_ROOT/deploy/dev/docker-compose.yml}"
LOKI_URL="${LOKI_URL:-http://127.0.0.1:13100/ready}"
GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:13000/api/health}"
ALLOY_URL="${ALLOY_URL:-http://127.0.0.1:13345/-/ready}"

log() { printf '[obs-health] %s\n' "$*"; }
fail() { printf '[obs-health] ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ -f "$COMPOSE_FILE" ] || fail "compose-файл не найден: $COMPOSE_FILE"

if [ "${DRY_RUN:-0}" = "1" ]; then
    log "dry-run: compose=$COMPOSE_FILE"
    log "dry-run: проверю сервисы loki, alloy, grafana и URL $LOKI_URL / $GRAFANA_URL / $ALLOY_URL"
    exit 0
fi

command -v docker >/dev/null 2>&1 || fail "docker не найден"
command -v curl >/dev/null 2>&1 || fail "curl не найден"

RUNNING="$(docker compose -f "$COMPOSE_FILE" ps --format '{{.Service}}' 2>/dev/null || true)"
for svc in loki alloy grafana; do
    grep -qx "$svc" <<<"$RUNNING" || fail "сервис $svc не запущен в $COMPOSE_FILE"
    log "сервис $svc: запущен"
done

for pair in "loki:$LOKI_URL" "grafana:$GRAFANA_URL" "alloy:$ALLOY_URL"; do
    name="${pair%%:*}"
    url="${pair#*:}"
    code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || true)"
    case "$code" in
        200|204|30[0-9]) log "$name $url → $code" ;;
        *) fail "$name $url → '$code' (ожидался 200/204/3xx)" ;;
    esac
done

log "контур Observability здоров"
