#!/usr/bin/env bash
# actionlint и zizmor: проверка синтаксиса и безопасности workflow-файлов.
set -euo pipefail

cd "$(dirname "$0")/.."

go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12
"$(go env GOPATH)/bin/actionlint" -color

uvx --from zizmor==1.33.1 zizmor .github/workflows --persona=regular
