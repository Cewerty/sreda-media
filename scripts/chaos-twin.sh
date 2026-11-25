#!/usr/bin/env bash
# Учебная smoke-имитация: не доказывает детектирование, доставку или восстановление.
# Поднимает локальный двойник, применяет сценарий и пишет отчёт во временный каталог.
# Не трогает прод, /srv, systemd и чужие контейнеры.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$REPO_ROOT/deploy/chaos/docker-compose.yml"
SCENARIO="${1:-stop-loki}"

if ! command -v docker >/dev/null 2>&1; then
    printf '[chaos] docker не найден: репетиция пропущена\n'
    exit 0
fi

case "$SCENARIO" in
    stop-loki|disk-full|stale-backup) ;;
    *)
        printf '[chaos] неизвестный сценарий: %s\n' "$SCENARIO" >&2
        exit 1
        ;;
esac

TMP="$(mktemp -d)"
cleanup() {
    docker compose -p sreda-chaos -f "$COMPOSE" down -v >/dev/null 2>&1 || true
    rm -rf "$TMP"
}
trap cleanup EXIT

docker compose -p sreda-chaos -f "$COMPOSE" up -d
"$REPO_ROOT/scripts/inject_fault.sh" "$SCENARIO" > "$TMP/fault.log" 2>&1
docker compose -p sreda-chaos -f "$COMPOSE" ps > "$TMP/ps.log" 2>&1
python3 "$REPO_ROOT/scripts/chaos_runbook_check.py" > "$TMP/runbook.log" 2>&1

{
    printf '# Хаос-репетиция: %s\n\n' "$SCENARIO"
    printf '## Инъекция\n\n```text\n'
    cat "$TMP/fault.log"
    printf '```\n\n## Состояние стека\n\n```text\n'
    cat "$TMP/ps.log"
    printf '```\n\n## Runbook\n\n```text\n'
    cat "$TMP/runbook.log"
    printf '```\n'
} > "$TMP/chaos-report.md"

cat "$TMP/chaos-report.md"
printf '[chaos] стек остановлен, временный каталог удалён по trap\n'
