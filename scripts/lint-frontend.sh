#!/usr/bin/env bash
# Run frontend linting with eslint.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Frontend Linting (eslint) ==="
cd "$PROJECT_ROOT/frontend"
npx eslint .
