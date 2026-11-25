#!/usr/bin/env bash
# Репетиция DR без `/srv` и systemd: только временные копии конфигурации.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

rpo=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["rpo_hours"])' "$REPO_ROOT/deploy/observability/slo.json")
if [ "$rpo" -gt 24 ]; then
    printf '[dr-drill] FAIL: RPO %s ч больше 24 ч\n' "$rpo" >&2
    exit 1
fi

for rel in deploy/observability/backup.service deploy/observability/backup.timer scripts/backup-observability.sh scripts/restore-observability.sh; do
    cp "$REPO_ROOT/$rel" "$tmp/$(basename "$rel")"
done
grep -q 'CONFIRM=1' "$tmp/restore-observability.sh" || { echo '[dr-drill] FAIL: нет guard CONFIRM=1' >&2; exit 1; }
grep -q 'OnCalendar=daily' "$tmp/backup.timer" || { echo '[dr-drill] FAIL: backup.timer не ежедневный' >&2; exit 1; }
# Default-пути /srv/sreda в скопированных конфигах — это данные, а не действия:
# проверяем реальные деструктивные вызовы, а не упоминания пути.
if grep -RqsE '((rm|mv|cp|chown|chmod)[[:space:]].*/srv/sreda|systemctl[[:space:]]+(start|stop|enable|disable|restart))' "$tmp"; then
    echo '[dr-drill] FAIL: репетиция не должна трогать /srv или systemd' >&2
    exit 1
fi
printf '[dr-drill] OK: RPO=%s ч, backup.timer daily, restore guard CONFIRM=1, временный каталог удалён\n' "$rpo"
