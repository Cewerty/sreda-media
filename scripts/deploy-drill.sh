#!/usr/bin/env bash
# Сквозная локальная репетиция выкладки статического артефакта (issue #7, ADR 0015).
#
#   scripts/deploy-drill.sh
#
# Прогоняет build-site -> stage-site -> sign/verify -> deploy x2 -> smoke -> rollback
# только во временном каталоге. Не трогает /srv, systemd, прод-адрес и ENABLE_*.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { printf '[deploy-drill] %s\n' "$*"; }
fail() { printf '[deploy-drill] FAIL: %s\n' "$*" >&2; exit 1; }

read -r -a JUST_CMD <<< "${JUST:-uvx --from rust-just just}"

command -v pnpm >/dev/null 2>&1 || fail "pnpm не найден: нужна среда Node/pnpm"
command -v python3 >/dev/null 2>&1 || fail "python3 не найден"
command -v curl >/dev/null 2>&1 || fail "curl не найден"
[ -d apps/site ] || fail "apps/site отсутствует"
[ -f apps/site/package.json ] || fail "apps/site/package.json отсутствует"

TMP=$(mktemp -d)
HTTP_PID=""
cleanup() {
    if [ -n "$HTTP_PID" ]; then
        kill "$HTTP_PID" >/dev/null 2>&1 || true
    fi
    rm -rf "$TMP"
}
trap cleanup EXIT

pnpm install --frozen-lockfile
"${JUST_CMD[@]}" build-site
"${JUST_CMD[@]}" stage-site
[ -f dist/index.html ] || fail "dist/index.html не создан stage-site"

ARTIFACT="$TMP/artifact"
mkdir -p "$ARTIFACT"
cp -a dist/. "$ARTIFACT/"
# Учебная заглушка: issue #5 остаётся зоной фронтенда, в git файл не попадает.
printf '<html><body>404</body></html>\n' > "$ARTIFACT/404.html"
log "создана учебная 404.html во временном артефакте (issue #5, не коммитится)"

"$REPO_ROOT/scripts/sign-artifact.sh" "$ARTIFACT"
"$REPO_ROOT/scripts/verify-artifact.sh" "$ARTIFACT"

RELEASES="$TMP/releases"
CURRENT="$TMP/current"
ARTIFACT_V2="$TMP/artifact-v2"
mkdir -p "$ARTIFACT_V2"
cp -a "$ARTIFACT/." "$ARTIFACT_V2/"
printf 'deploy drill v2\n' > "$ARTIFACT_V2/drill-v2.txt"

bash "$REPO_ROOT/scripts/deploy-static.sh" deploy "$ARTIFACT" "$RELEASES" "$CURRENT"
sleep 1
bash "$REPO_ROOT/scripts/deploy-static.sh" deploy "$ARTIFACT_V2" "$RELEASES" "$CURRENT"
[ -L "$CURRENT" ] || fail "current не является симлинком"

PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
python3 -m http.server "$PORT" --directory "$CURRENT" >"$TMP/http.log" 2>&1 &
HTTP_PID=$!
curl --retry 10 --retry-connrefused --retry-delay 1 -fsS "http://127.0.0.1:$PORT/" >/dev/null
env -u SREDA_SMOKE_MARKER "$REPO_ROOT/scripts/smoke-static.sh" "http://127.0.0.1:$PORT"
kill "$HTTP_PID" >/dev/null 2>&1 || true
HTTP_PID=""

FIRST_RELEASE=$(cat "$RELEASES/.previous")
bash "$REPO_ROOT/scripts/deploy-static.sh" rollback "$RELEASES" "$CURRENT"
[ "$(readlink "$CURRENT")" = "$FIRST_RELEASE" ] || fail "откат не вернул первый релиз"
[ -f "$CURRENT/index.html" ] || fail "после отката нет index.html"

log "успешно: сборка, подпись, две выкладки, smoke и откат во временном каталоге"
log "прод-пути, гейты и внешние сервисы не использовались; временные файлы удаляются"
