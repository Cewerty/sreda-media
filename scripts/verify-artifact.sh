#!/usr/bin/env bash
# Сверка хэша и (если есть) keyless-подписи статического артефакта.
# Неблокирующая локальная операция: в verify и CI не входит.
# Использование: scripts/verify-artifact.sh dist/
set -euo pipefail

ARTIFACT="${1:-dist}"
fail() { printf '[verify-artifact] ОШИБКА: %s\n' "$*" >&2; exit 1; }
log() { printf '[verify-artifact] %s\n' "$*"; }

[ -d "$ARTIFACT" ] || fail "нет каталога $ARTIFACT"
[ -f "$ARTIFACT/artifact.sha256" ] || fail "нет artifact.sha256 в $ARTIFACT"
[ -f "$ARTIFACT/artifact.tar.gz" ] || fail "нет artifact.tar.gz в $ARTIFACT"

( cd "$ARTIFACT" && sha256sum -c artifact.sha256 ) || fail "SHA256 не совпал"

if [ -f "$ARTIFACT/cosign.sig" ] && [ -f "$ARTIFACT/cosign.pem" ]; then
    if command -v cosign >/dev/null 2>&1; then
        cosign verify-blob \
            --certificate "$ARTIFACT/cosign.pem" \
            --signature "$ARTIFACT/cosign.sig" \
            "$ARTIFACT/artifact.tar.gz" || fail "проверка cosign не пройдена"
        log "SHA256 и cosign подпись корректны"
    else
        log "SHA256 корректен; cosign не установлен — подпись не проверена"
    fi
else
    log "SHA256 корректен; файлов подписи нет (cosign не запускался) — пропускаю подпись"
fi
