#!/usr/bin/env bash
# Учебная smoke-имитация: не включает алерты и не меняет прод.
# Инъекция отказа в локальный хаос-стек. Только внутри sreda-chaos.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$REPO_ROOT/deploy/chaos/docker-compose.yml"
SCENARIO="${1:-}"

case "$SCENARIO" in
  stop-loki)
    docker compose -p sreda-chaos -f "$COMPOSE" stop loki
    printf '[chaos] loki остановлен\n'
    ;;
  disk-full)
    docker compose -p sreda-chaos -f "$COMPOSE" exec -T probe \
      sh -c 'dd if=/dev/zero of=/tmp/chaos-fill bs=1M count=8 status=none'
    printf '[chaos] временный диск заполнен 8MiB внутри probe\n'
    ;;
  stale-backup)
    docker compose -p sreda-chaos -f "$COMPOSE" exec -T probe \
      sh -c 'touch -d "@$(( $(date +%s) - 172800 ))" /tmp/chaos-stale-backup && stat -c %y /tmp/chaos-stale-backup'
    printf '[chaos] метка времени бэкапа состарена на 2 дня\n'
    ;;
  *)
    printf '[chaos] неизвестный сценарий: %s\n' "$SCENARIO" >&2
    exit 1
    ;;
esac
