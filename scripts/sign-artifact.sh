#!/usr/bin/env bash
# Подготовка keyless-подписи статического артефакта через cosign (issue #7/#14).
# В CI вызывается неблокирующим шагом site-build (continue-on-error), в verify не входит.
# Без cosign/OIDC честно пропускает. Использование: scripts/sign-artifact.sh dist/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT="${1:-dist}"
[ -d "$ARTIFACT" ] || { printf '[sign] ОШИБКА: нет каталога %s\n' "$ARTIFACT" >&2; exit 1; }

# Хэш готовится всегда: verify-artifact должен работать и без cosign/OIDC.
TARBALL="$ARTIFACT/artifact.tar.gz"
tar czf "$TARBALL" -C "$ARTIFACT" --exclude='artifact.tar.gz' --exclude='artifact.sha256' \
    --exclude='cosign.sig' --exclude='cosign.pem' .
(
    cd "$ARTIFACT"
    sha256sum artifact.tar.gz > artifact.sha256
)
printf '[sign] SHA256 подготовлен: %s/artifact.sha256\n' "$ARTIFACT"

if ! command -v cosign >/dev/null 2>&1; then
    printf '[sign] cosign не установлен: подпись пропущена, хэш остался\n'
    exit 0
fi

cosign sign-blob --yes --output-signature "$ARTIFACT/cosign.sig" \
    --output-certificate "$ARTIFACT/cosign.pem" "$TARBALL"
printf '[sign] подпись подготовлена: %s/cosign.sig, %s/cosign.pem\n' \
    "$ARTIFACT" "$ARTIFACT"
