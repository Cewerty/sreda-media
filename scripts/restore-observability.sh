#!/usr/bin/env bash
# Восстановление бэкапа observability по UTC-префиксу (issue #14, 0.2).
# ВАЖНО: операция деструктивна — перезаписывает таблицы и volume Grafana.
# Использование: CONFIRM=1 scripts/restore-observability.sh 20261125T120000Z [--sql-only]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${OBS_COMPOSE_FILE:-$REPO_ROOT/deploy/observability/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-/srv/sreda/backups}"
DRY_RUN="${DRY_RUN:-0}"
CONFIRM="${CONFIRM:-0}"
PGPASSWORD_VALUE="${POSTGRES_OBSERVABILITY_PASSWORD:-change-me}"
PREFIX="${1:-}"
MODE="${2:-}"

fail() { printf '[restore] ОШИБКА: %s\n' "$*" >&2; exit 1; }
log() { printf '[restore] %s\n' "$*"; }

[ -n "$PREFIX" ] || fail "нужен UTC-префикс бэкапа, например 20261125T120000Z"
case "$MODE" in
    ""|--sql-only) ;;
    *) fail "неизвестный режим: $MODE" ;;
esac

SQL_FILE="$BACKUP_DIR/${PREFIX}-observability.sql.gz"
GRAFANA_FILE="$BACKUP_DIR/${PREFIX}-grafana.tar.gz"
MANIFEST="$BACKUP_DIR/${PREFIX}-manifest.sha256"

if [ "$DRY_RUN" != "1" ]; then
    [ -f "$SQL_FILE" ] || fail "нет SQL-дампа: $SQL_FILE"
    if [ "$MODE" != "--sql-only" ]; then
        [ -f "$GRAFANA_FILE" ] || fail "нет архива Grafana: $GRAFANA_FILE"
    fi
fi

if [ "$DRY_RUN" = "1" ]; then
    log "dry-run: восстановить SQL из $SQL_FILE"
    if [ "$MODE" != "--sql-only" ]; then
        log "dry-run: остановить grafana, распаковать $GRAFANA_FILE, поднять grafana"
    fi
    log "dry-run: манифест $MANIFEST"
    exit 0
fi

[ "$CONFIRM" = "1" ] || fail "деструктивная операция: установите CONFIRM=1 для продолжения"
command -v docker >/dev/null 2>&1 || fail "docker не найден"
[ -f "$COMPOSE_FILE" ] || fail "compose-файл не найден: $COMPOSE_FILE"

if [ -f "$MANIFEST" ]; then
    ( cd "$BACKUP_DIR" && sha256sum -c "$(basename "$MANIFEST")" ) \
        || fail "проверка SHA256 не пройдена"
else
    log "манифест не найден, продолжаем по явному указанию: $MANIFEST"
fi

log "восстанавливаем SQL из $(basename "$SQL_FILE")"
gunzip -c "$SQL_FILE" | docker compose -f "$COMPOSE_FILE" exec -T \
    -e PGPASSWORD="$PGPASSWORD_VALUE" postgres \
    psql -U observability -d observability -v ON_ERROR_STOP=1

if [ "$MODE" != "--sql-only" ]; then
    log "останавливаем grafana и восстанавливаем volume"
    docker compose -f "$COMPOSE_FILE" stop grafana
    docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
        -v "$GRAFANA_FILE:/backup.tar.gz:ro" \
        --entrypoint sh grafana \
        -c 'tar xzf /backup.tar.gz -C /var/lib/grafana'
    docker compose -f "$COMPOSE_FILE" start grafana
fi

log "готово: $(basename "$SQL_FILE") восстановлен"
