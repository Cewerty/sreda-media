#!/usr/bin/env bash
# Сборка документации MkDocs в ISO-чистом временном каталоге (issue #35).
# Входит в just verify, но не публикует страницы: ENABLE_DOCS_PAGES не нужен.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

cd "$REPO_ROOT"
uvx --from mkdocs-material==9.8.2 mkdocs build --strict --site-dir "$tmp/site"
printf '[docs-build] MkDocs strict: OK (временный каталог удалён)\n'
