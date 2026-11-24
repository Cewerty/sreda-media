#!/usr/bin/env bash
# Диагностика локального инструментария. Никогда не падает: это справка, не гейд.
set -uo pipefail
printf '%-18s %s\n' 'ИНСТРУМЕНТ' 'ВЕРСИЯ'
for name in python3 uv pnpm node go just gh docker caddy systemd-analyze gitleaks cosign; do
    if command -v "$name" >/dev/null 2>&1; then
        version=$("$name" --version 2>/dev/null | head -n 1 || true)
        printf '%-18s %s\n' "$name" "${version:-установлен}"
    else
        printf '%-18s %s\n' "$name" 'не найден'
    fi
done
exit 0
