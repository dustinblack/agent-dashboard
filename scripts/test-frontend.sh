#!/usr/bin/env bash
# Run frontend unit tests with vitest and coverage.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Frontend Unit Tests (vitest + v8 coverage) ==="
cd "$PROJECT_ROOT/frontend"
npx vitest run --coverage
