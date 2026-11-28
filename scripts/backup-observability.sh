#!/usr/bin/env bash
# Резервная копия операционных событий PostgreSQL и данных Grafana (issue #14, 0.2).
# Создаёт два сжатых файла и манифест SHA256 с UTC-меткой. Ничего не отправляет во внешние системы.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${OBS_COMPOSE_FILE:-$REPO_ROOT/deploy/observability/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-/srv/sreda/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
MIN_KEEP="${MIN_KEEP:-2}"
DRY_RUN="${DRY_RUN:-0}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FRESHNESS_FILE="${SREDA_FRESHNESS_FILE:-/srv/sreda/backups/textfile/sreda.prom}"
SQL_FILE=""
GRAFANA_FILE=""
MANIFEST=""

log() { printf '[backup] %s\n' "$*"; }
fail() { printf '[backup] ОШИБКА: %s\n' "$*" >&2; exit 1; }

# Структурированные события для Alloy -> Loki. Ничего не мешает basic-стеку:
# файл опциональный, права и каталог задаются окружением на VPS.
BACKUP_LOG="${SREDA_BACKUP_LOG:-/var/log/sreda/backup.jsonl}"
emit() {
    [ "$DRY_RUN" = "1" ] && return 0
    mkdir -p "$(dirname "$BACKUP_LOG")" 2>/dev/null || return 0
    printf '{"component":"backup","environment":"production","event":"%s","outcome":"%s","release":"%s","timestamp":"%s"}\n' \
        "$1" "$2" "$TS" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$BACKUP_LOG" 2>/dev/null || true
}
cleanup() {
    status=$?
    if [ "$status" -ne 0 ] && [ "$DRY_RUN" != "1" ]; then
        emit backup_failed failure
    fi
    for partial in "${SQL_FILE}.partial" "${GRAFANA_FILE}.partial" "${MANIFEST}.partial"; do
        [ -n "$partial" ] && rm -f -- "$partial" 2>/dev/null || true
    done
    return 0
}
trap cleanup EXIT

write_freshness() {
    [ "$DRY_RUN" != "1" ] || return 0
    mkdir -p "$(dirname "$FRESHNESS_FILE")" || return 0
    printf 'backup_last_success_timestamp %s\n' "$(date +%s)" \
        > "${FRESHNESS_FILE}.tmp" && mv -f "${FRESHNESS_FILE}.tmp" "$FRESHNESS_FILE" || true
}

command -v docker >/dev/null 2>&1 || fail "docker не найден"
[ -f "$COMPOSE_FILE" ] || fail "compose-файл не найден: $COMPOSE_FILE"
if [ "$DRY_RUN" != "1" ]; then
    : "${POSTGRES_OBSERVABILITY_PASSWORD:?set POSTGRES_OBSERVABILITY_PASSWORD}"
fi
PGPASSWORD_VALUE="${POSTGRES_OBSERVABILITY_PASSWORD:-change-me}"
emit backup_started running

if [ "$DRY_RUN" != "1" ]; then
    install -d -m 0700 "$BACKUP_DIR"
fi

SQL_FILE="$BACKUP_DIR/${TS}-observability.sql.gz"
GRAFANA_FILE="$BACKUP_DIR/${TS}-grafana.tar.gz"
MANIFEST="$BACKUP_DIR/${TS}-manifest.sha256"
AGE_RECIPIENT="${SREDA_BACKUP_AGE_RECIPIENT:-}"

# PostgreSQL уже включён в профиле sql; если сервис не поднят, шаг честно падает.
if [ "$DRY_RUN" = "1" ]; then
    log "pg_dump postgres -> $SQL_FILE"
else
    log "pg_dump postgres -> $SQL_FILE"
    docker compose -f "$COMPOSE_FILE" exec -T -e PGPASSWORD="$PGPASSWORD_VALUE" postgres \
        pg_dump -U observability -d observability --no-owner --clean --if-exists \
        | gzip -9 > "${SQL_FILE}.partial"
    [ -s "${SQL_FILE}.partial" ] || fail "пустой SQL-дамп"
    gzip -t "${SQL_FILE}.partial" || fail "повреждён SQL-дамп"
    mv -f "${SQL_FILE}.partial" "$SQL_FILE"
fi

# Grafana хранит пользовательские алерты, настройки и сессии в своём volume.
# Provisioning-файлы витрины лежат в репозитории, поэтому копируется только volume.
if [ "$DRY_RUN" = "1" ]; then
    log "tar /var/lib/grafana -> $GRAFANA_FILE"
else
    log "tar /var/lib/grafana -> $GRAFANA_FILE"
    docker compose -f "$COMPOSE_FILE" exec -T grafana \
        sh -c 'tar czf - -C /var/lib/grafana .' > "${GRAFANA_FILE}.partial"
    [ -s "${GRAFANA_FILE}.partial" ] || fail "пустой архив Grafana"
    gzip -t "${GRAFANA_FILE}.partial" || fail "повреждён архив Grafana"
    mv -f "${GRAFANA_FILE}.partial" "$GRAFANA_FILE"
fi

# Опциональное шифрование: если задан получатель age, открытые дампы не остаются на диске.
if [ -n "$AGE_RECIPIENT" ]; then
    command -v age >/dev/null 2>&1 || fail "age не найден, но задан SREDA_BACKUP_AGE_RECIPIENT"
    log "шифрование age включено"
    if [ "$DRY_RUN" != "1" ]; then
        age -r "$AGE_RECIPIENT" -o "${SQL_FILE}.age" "$SQL_FILE"
        age -r "$AGE_RECIPIENT" -o "${GRAFANA_FILE}.age" "$GRAFANA_FILE"
        rm -f "$SQL_FILE" "$GRAFANA_FILE"
    fi
    SQL_FILE="${SQL_FILE}.age"
    GRAFANA_FILE="${GRAFANA_FILE}.age"
fi

if [ "$DRY_RUN" = "1" ]; then
    log "dry-run: каталог $BACKUP_DIR, retention ${RETENTION_DAYS} дней"
    log "dry-run: манифест $MANIFEST"
    exit 0
fi

(
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$SQL_FILE")" "$(basename "$GRAFANA_FILE")" \
        > "$(basename "${MANIFEST}.partial")"
)
mv -f "${MANIFEST}.partial" "$MANIFEST"

declare -A PROTECT=()
while IFS= read -r manifest; do
    prefix="${manifest%-manifest.sha256}"
    PROTECT["$prefix"]=1
done < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f -name '*-manifest.sha256' \
        -printf '%T@ %f\n' | sort -nr | head -n "$MIN_KEEP" | cut -d' ' -f2-
)

while IFS= read -r -d '' candidate; do
    base="$(basename "$candidate")"
    prefix="${base%%-*}"
    if [ -n "${PROTECT[$prefix]:-}" ]; then
        emit backup_retention_skipped skipped
        continue
    fi
    rm -f -- "$candidate"
done < <(
    find "$BACKUP_DIR" -maxdepth 1 -type f \
        \( -name '*-observability.sql.gz' -o -name '*-observability.sql.gz.age' \
           -o -name '*-grafana.tar.gz' -o -name '*-grafana.tar.gz.age' \
           -o -name '*-manifest.sha256' \) \
        -mtime "+${RETENTION_DAYS}" -print0
)

emit backup_finished success
write_freshness
log "готово: $(basename "$SQL_FILE"), $(basename "$GRAFANA_FILE"), $(basename "$MANIFEST")"
