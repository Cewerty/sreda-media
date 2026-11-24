#!/usr/bin/env bash
# Резервная копия операционных событий PostgreSQL и данных Grafana (issue #14, 0.2).
# Создаёт два сжатых файла и манифест SHA256 с UTC-меткой. Ничего не отправляет во внешние системы.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${OBS_COMPOSE_FILE:-$REPO_ROOT/deploy/observability/docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-/srv/sreda/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DRY_RUN="${DRY_RUN:-0}"
PGPASSWORD_VALUE="${POSTGRES_OBSERVABILITY_PASSWORD:-change-me}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"

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
trap 'emit backup_failed failure' ERR

command -v docker >/dev/null 2>&1 || fail "docker не найден"
[ -f "$COMPOSE_FILE" ] || fail "compose-файл не найден: $COMPOSE_FILE"
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
        | gzip -9 > "$SQL_FILE"
    gzip -t "$SQL_FILE" || fail "повреждён SQL-дамп"
fi

# Grafana хранит пользовательские алерты, настройки и сессии в своём volume.
# Provisioning-файлы витрины лежат в репозитории, поэтому копируется только volume.
if [ "$DRY_RUN" = "1" ]; then
    log "tar /var/lib/grafana -> $GRAFANA_FILE"
else
    log "tar /var/lib/grafana -> $GRAFANA_FILE"
    docker compose -f "$COMPOSE_FILE" exec -T grafana \
        sh -c 'tar czf - -C /var/lib/grafana .' > "$GRAFANA_FILE"
    gzip -t "$GRAFANA_FILE" || fail "повреждён архив Grafana"
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
    sha256sum "$(basename "$SQL_FILE")" "$(basename "$GRAFANA_FILE")" > "$(basename "$MANIFEST")"
)

find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name '*-observability.sql.gz' -o -name '*-observability.sql.gz.age' \
       -o -name '*-grafana.tar.gz' -o -name '*-grafana.tar.gz.age' \
       -o -name '*-manifest.sha256' \) \
    -mtime "+${RETENTION_DAYS}" -delete

emit backup_finished success
log "готово: $(basename "$SQL_FILE"), $(basename "$GRAFANA_FILE"), $(basename "$MANIFEST")"
