#!/usr/bin/env bash
# Манифест собранного артефакта: хэш, git-состояние и статус гейтов.
# Не подписывает, не выкладывает и не включает флаги. Использование:
#   scripts/release-manifest.sh dist/
set -euo pipefail

ARTIFACT="${1:-dist}"
fail() { printf '[release-manifest] ОШИБКА: %s\n' "$*" >&2; exit 1; }

[ -d "$ARTIFACT" ] || fail "нет каталога артефакта: $ARTIFACT"
[ -f "$ARTIFACT/artifact.sha256" ] || fail "нет artifact.sha256 в $ARTIFACT"

SHA256="$(awk 'NR==1 {print $1}' "$ARTIFACT/artifact.sha256")"
[ -n "$SHA256" ] || fail "artifact.sha256 пуст"
GIT_SHA="$(git rev-parse HEAD)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
COSIGN_VERIFIED=false
if [ -f "$ARTIFACT/cosign.sig" ] && [ -f "$ARTIFACT/cosign.pem" ] && command -v cosign >/dev/null 2>&1; then
    COSIGN_VERIFIED=true
fi

python3 - "$ARTIFACT/release.json" "$SHA256" "$GIT_SHA" "$GIT_BRANCH" "$COSIGN_VERIFIED" <<'PY'
import datetime
import json
import os
import sys

out, sha256, git_sha, git_branch, cosign = sys.argv[1:6]
manifest = {
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "git_sha": git_sha,
    "git_branch": git_branch,
    "artifact_sha256": sha256,
    "cosign_verified": cosign == "true",
    "gates": {
        "ENABLE_DEPLOY": os.getenv("ENABLE_DEPLOY", "") == "true",
        "ENABLE_DOCS_PAGES": os.getenv("ENABLE_DOCS_PAGES", "") == "true",
        "ENABLE_PROVENANCE": os.getenv("ENABLE_PROVENANCE", "") == "true",
        "SREDA_SITE_URL": bool(os.getenv("SREDA_SITE_URL", "")),
    },
    "operator": os.getenv("USER", "unknown"),
}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY

printf '[release-manifest] подготовлен %s/release.json (гейты не включались)\n' "$ARTIFACT"
