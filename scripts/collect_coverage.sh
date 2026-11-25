#!/usr/bin/env bash
# Неблокирующий сбор отчётов покрытия. Не меняет Sue-код и зависимости проектов.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${COVERAGE_DIR:-$REPO_ROOT/coverage-reports}"
mkdir -p "$OUT"
cd "$REPO_ROOT"

if [ -f pnpm-lock.yaml ] && command -v pnpm >/dev/null 2>&1; then
    if pnpm --filter @sreda/cms-web exec vitest run --coverage >"$OUT/vitest.log" 2>&1; then
        echo "coverage: vitest ok"
    else
        echo "coverage: vitest --coverage недоступен (нужен @vitest/coverage-v8), пропускаю" >&2
    fi
else
    echo "coverage: pnpm недоступен, пропускаю vitest" >&2
fi

if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
    if uv run --project apps/cms-api python -m pytest apps/cms-api/tests -q --cov=apps/cms-api >"$OUT/pytest.log" 2>&1; then
        echo "coverage: pytest ok"
    else
        echo "coverage: pytest --cov недоступен (нужен pytest-cov) или тестов нет, пропускаю" >&2
    fi
else
    echo "coverage: uv недоступен, пропускаю pytest" >&2
fi

sha256sum "$OUT"/*.log > "$OUT/SHA256SUMS" 2>/dev/null || true
echo "coverage: отчёты в $OUT"
