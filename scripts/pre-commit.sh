#!/usr/bin/env bash
# Неблокирующий локальный pre-commit: только чтение и проверки репозитория.
# Не installing хуки, не меняет индекс — запускается вручную.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

python3 scripts/check.py
python3 scripts/check_log_schema.py
python3 scripts/check_uptime_config.py
python3 scripts/check_links.py
for f in scripts/*.sh; do bash -n "$f"; done

if command -v gitleaks >/dev/null 2>&1; then
    gitleaks git --redact --no-banner
else
    echo '[pre-commit] gitleaks не найден: пропускаю scan'
fi
echo '[pre-commit] проверки пройдены'
