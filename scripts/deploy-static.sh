#!/usr/bin/env bash
# Атомарная выкладка статического артефакта и откат (ADR 0015, issue #7).
#
#   deploy-static.sh deploy <artifact-dir> <releases-dir> <current-link>
#   deploy-static.sh rollback <releases-dir> <current-link>
#   deploy-static.sh verify <base-url> [previous-release-dir]
#
# Артефакт не изменяется после копирования. Указатель current меняется только
# после проверки состава нового релиза. Предыдущий релиз сохраняется для отката.
set -euo pipefail

log() { printf '[deploy] %s\n' "$*" >&2; }
die() { printf '[deploy] FAIL: %s\n' "$*" >&2; exit 1; }

cmd=${1:-}
case "$cmd" in
  deploy)
    artifact=${2:?usage: deploy <artifact-dir> <releases-dir> <current-link>}
    releases=${3:?}
    current=${4:?}
    [ -d "$artifact" ] || die "нет каталога артефакта: $artifact"
    [ -f "$artifact/index.html" ] || die "в артефакте нет index.html"
    [ -f "$artifact/404.html" ] || die "в артефакте нет 404.html (обязательно по #7)"
    mkdir -p "$releases"

    stamp=$(date -u +%Y%m%dT%H%M%SZ)
    release="$releases/$stamp"
    [ ! -e "$release" ] || die "релиз уже существует: $release"
    tmp="$releases/.incoming-$stamp"
    rm -rf "$tmp"
    mkdir -p "$tmp"
    cp -a "$artifact/." "$tmp/"
    # Проверяем состав до переключения указателя.
    [ -f "$tmp/index.html" ] || die "копия без index.html"
    [ -f "$tmp/404.html" ] || die "копия без 404.html"
    mv "$tmp" "$release"

    previous=""
    if [ -L "$current" ]; then
      previous=$(readlink "$current" || true)
    fi
    ln -sfn "$release" "$current.new"
    mv -Tf "$current.new" "$current"
    printf '%s\n' "$previous" > "$releases/.previous"
    log "развёрнут $release (предыдущий: ${previous:-нет})"
    ;;

  rollback)
    releases=${2:?usage: rollback <releases-dir> <current-link>}
    current=${3:?}
    previous=""
    [ -f "$releases/.previous" ] && previous=$(cat "$releases/.previous")
    [ -n "$previous" ] && [ -d "$previous" ] || die "нет предыдущего релиза для отката"
    ln -sfn "$previous" "$current.new"
    mv -Tf "$current.new" "$current"
    log "откат выполнен: $current -> $previous"
    ;;

  verify)
    base=${2:?usage: verify <base-url> [previous-release-dir]}
    previous=${3:-}
    main_code=$(curl -fsS -o /dev/null -w '%{http_code}' "$base/" || true)
    missing_code=$(curl -sS -o /dev/null -w '%{http_code}' "$base/this-page-does-not-exist" || true)
    log "main=$main_code 404=$missing_code"
    [ "$main_code" = "200" ] || die "главная отдаёт $main_code"
    [ "$missing_code" = "404" ] || die "несуществующая страница отдаёт $missing_code"
    if [ -n "$previous" ]; then
      grep -q 'Sreda Media' "$previous/index.html" || die "в предыдущем релизе нет ожидаемого контента"
    fi
    log "проверка пройдена"
    ;;

  *)
    printf 'usage: %s {deploy|rollback|verify} ...\n' "$0" >&2
    exit 2
    ;;
esac
