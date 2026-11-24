#!/usr/bin/env bash
# Подготовка подписи статического артефакта через cosign keyless (issue #7/#14).
# В CI вызывается неблокирующим шагом site-build; в verify НЕ входит.
# Без cosign или без OIDC шаг честно пропускает подпись, не ломая сборку.
# Использование: scripts/sign-artifact.sh dist/
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT="${1:-dist}"
[ -d "$ARTIFACT" ] || { printf '[sign] ОШИБКА: нет каталога %s\n' "$ARTIFACT" >&2; exit 1; }
command -v cosign >/dev/null 2>&1 || { printf '[sign] cosign не установлен: пропускаю подготовку\n'; exit 0; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TARBALL="$TMP/artifact.tar.gz"
tar czf "$TARBALL" -C "$ARTIFACT" .
sha256sum "$TARBALL" > "$TMP/artifact.sha256"
cosign sign-blob --yes --output-signature "$ARTIFACT/cosign.sig" \
    --output-certificate "$ARTIFACT/cosign.pem" "$TARBALL"
cp "$TMP/artifact.sha256" "$ARTIFACT/artifact.sha256"
printf '[sign] подпись подготовлена: %s/cosign.sig, %s/cosign.pem\n' "$ARTIFACT" "$ARTIFACT"
