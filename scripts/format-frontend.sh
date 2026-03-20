#!/usr/bin/env bash
# Check frontend formatting with prettier.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Frontend Formatting (prettier) ==="
cd "$PROJECT_ROOT/frontend"
npx prettier --check "src/**/*.{ts,tsx,css}"
