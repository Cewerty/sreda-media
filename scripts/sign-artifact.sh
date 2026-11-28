#!/usr/bin/env bash
# Подготовка keyless-подписи статического артефакта через cosign (issue #7/#14).
# В CI вызывается неблокирующим шагом site-build (continue-on-error), в verify не входит.
# Без cosign/OIDC честно пропускает. Использование: scripts/sign-artifact.sh dist/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT="${1:-dist}"
[ -d "$ARTIFACT" ] || { printf '[sign] ОШИБКА: нет каталога %s\n' "$ARTIFACT" >&2; exit 1; }
[ -f "$ARTIFACT/index.html" ] || { printf '[sign] ОШИБКА: нет index.html\n' >&2; exit 1; }
[ -f "$ARTIFACT/404.html" ] || { printf '[sign] ОШИБКА: нет 404.html (issue #7)\n' >&2; exit 1; }

output() {
    printf '%s\n' "$1"
    [ -n "${GITHUB_OUTPUT:-}" ] && printf '%s\n' "$1" >> "$GITHUB_OUTPUT" || true
}

# Хэш готовится всегда: verify-artifact должен работать и без cosign/OIDC.
# Архив детерминирован: сортировка путей, фиксированные mtime/владелец, gzip -n.
TARBALL="$ARTIFACT/artifact.tar.gz"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -C "$ARTIFACT" --exclude='artifact.tar.gz' --exclude='artifact.sha256' \
    --exclude='cosign.sig' --exclude='cosign.pem' -cf - . \
    | gzip -n > "${TARBALL}.partial"
mv -f "${TARBALL}.partial" "$TARBALL"
(
    cd "$ARTIFACT"
    sha256sum artifact.tar.gz > artifact.sha256
)
output "artifact.sha256=$(awk '{print $1}' "$ARTIFACT/artifact.sha256")"
printf '[sign] SHA256 подготовлен: %s/artifact.sha256\n' "$ARTIFACT"

if ! command -v cosign >/dev/null 2>&1; then
    output 'signature.status=skipped_no_cosign'
    printf '[sign] cosign не установлен: подпись пропущена, хэш остался\n'
    exit 0
fi

cosign sign-blob --yes --output-signature "$ARTIFACT/cosign.sig" \
    --output-certificate "$ARTIFACT/cosign.pem" "$TARBALL"
output 'signature.status=signed'
printf '[sign] подпись подготовлена: %s/cosign.sig, %s/cosign.pem\n' \
    "$ARTIFACT" "$ARTIFACT"
