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
AGE_IDENTITY="${SREDA_BACKUP_AGE_IDENTITY:-}"
PREFIX="${1:-}"
MODE="${2:-}"
TMP_DIR=""

fail() { printf '[restore] ОШИБКА: %s\n' "$*" >&2; exit 1; }
log() { printf '[restore] %s\n' "$*"; }
START_TS="$(date +%s)"
RESTORE_LOG="${SREDA_BACKUP_LOG:-/var/log/sreda/backup.jsonl}"
emit() {
    [ "$DRY_RUN" != "1" ] || return 0
    mkdir -p "$(dirname "$RESTORE_LOG")" 2>/dev/null || return 0
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{"component":"backup","environment":"production","event":"%s","outcome":"%s","release":"%s","timestamp":"%s","elapsed_ms":"%s"}\n' \
        "$1" "$2" "$now" "$now" \
        "$((($(date +%s) - START_TS) * 1000))" >> "$RESTORE_LOG" 2>/dev/null || true
}
cleanup() { if [ -n "$TMP_DIR" ] && [ -d "$TMP_DIR" ]; then rm -rf "$TMP_DIR"; fi; return 0; }
trap cleanup EXIT

# Возвращает путь к открытому файлу: либо исходный, либо расшифрованный во temp.
resolve_file() {
    base="$1"
    if [ -f "$base" ]; then
        printf '%s' "$base"
        return 0
    fi
    if [ -f "${base}.age" ]; then
        [ -n "$AGE_IDENTITY" ] || fail "файл зашифрован, но SREDA_BACKUP_AGE_IDENTITY не задан"
        command -v age >/dev/null 2>&1 || fail "age не найден для расшифровки бэкапа"
        [ -n "$TMP_DIR" ] || TMP_DIR="$(mktemp -d)"
        out="$TMP_DIR/$(basename "$base")"
        age -d -i "$AGE_IDENTITY" -o "$out" "${base}.age" || fail "не удалось расшифровать ${base}.age"
        printf '%s' "$out"
        return 0
    fi
    return 1
}

[ -n "$PREFIX" ] || fail "нужен UTC-префикс бэкапа, например 20261125T120000Z"
case "$MODE" in
    ""|--sql-only) ;;
    *) fail "неизвестный режим: $MODE" ;;
esac

SQL_FILE="$BACKUP_DIR/${PREFIX}-observability.sql.gz"
GRAFANA_FILE="$BACKUP_DIR/${PREFIX}-grafana.tar.gz"
MANIFEST="$BACKUP_DIR/${PREFIX}-manifest.sha256"

if [ "$DRY_RUN" != "1" ]; then
    { [ -f "$SQL_FILE" ] || [ -f "${SQL_FILE}.age" ]; } || fail "нет SQL-дампа: $SQL_FILE"
    if [ "$MODE" != "--sql-only" ]; then
        { [ -f "$GRAFANA_FILE" ] || [ -f "${GRAFANA_FILE}.age" ]; } || fail "нет архива Grafana: $GRAFANA_FILE"
    fi
fi

if [ "$DRY_RUN" = "1" ]; then
    log "dry-run: восстановить SQL из $SQL_FILE (или ${SQL_FILE}.age)"
    if [ "$MODE" != "--sql-only" ]; then
        log "dry-run: остановить grafana, распаковать $GRAFANA_FILE (или ${GRAFANA_FILE}.age), поднять grafana"
    fi
    log "dry-run: манифест $MANIFEST"
    exit 0
fi

[ "$CONFIRM" = "1" ] || fail "деструктивная операция: установите CONFIRM=1 для продолжения"
command -v docker >/dev/null 2>&1 || fail "docker не найден"
[ -f "$COMPOSE_FILE" ] || fail "compose-файл не найден: $COMPOSE_FILE"

if [ -f "$MANIFEST" ]; then
    ( cd "$BACKUP_DIR" && sha256sum -c "$(basename "$MANIFEST")" ) \
        || { emit restore_failed failure; fail "проверка SHA256 не пройдена"; }
else
    [ "${ALLOW_UNVERIFIED_RESTORE:-0}" = "1" ] || \
        { emit restore_failed failure; fail "манифест не найден: $MANIFEST"; }
    log "ВНИМАНИЕ: восстановление без манифеста разрешено явно"
    emit restore_unverified skipped
fi

SQL_FILE="$(resolve_file "$SQL_FILE")" || fail "не удалось подготовить SQL-дамп"
if [ "$MODE" != "--sql-only" ]; then
    GRAFANA_FILE="$(resolve_file "$GRAFANA_FILE")" || fail "не удалось подготовить архив Grafana"
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

emit restore_finished success
log "готово: $(basename "$SQL_FILE") восстановлен"
