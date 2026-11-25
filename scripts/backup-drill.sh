#!/usr/bin/env bash
# Проверка backup/restore без PostgreSQL, Docker-демона и внешних путей (issue #14).
# Работает во временном каталоге и только в DRY_RUN=1: ничего не деплоит и не удаляет.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() { printf '[backup-drill] %s\n' "$*"; }

log "проверка backup-observability.sh в DRY_RUN"
DRY_RUN=1 BACKUP_DIR="$TMP_DIR" "$REPO_ROOT/scripts/backup-observability.sh"

log "проверка restore-observability.sh в DRY_RUN (полное восстановление)"
DRY_RUN=1 BACKUP_DIR="$TMP_DIR" "$REPO_ROOT/scripts/restore-observability.sh" 19700101T000000Z

log "проверка restore-observability.sh в DRY_RUN (только SQL)"
DRY_RUN=1 BACKUP_DIR="$TMP_DIR" "$REPO_ROOT/scripts/restore-observability.sh" 19700101T000000Z --sql-only

# Локальная проверка механики манифеста без обращения к бэкенду.
printf 'sreda backup drill\n' > "$TMP_DIR/probe.txt"
(
    cd "$TMP_DIR"
    sha256sum probe.txt > probe.sha256
    sha256sum -c probe.sha256
)

log "готово: DRY_RUN backup/restore и SHA256-манифест прошли проверку"
