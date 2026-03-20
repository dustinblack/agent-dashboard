#!/usr/bin/env bash
# Run TypeScript type checking.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== TypeScript Type Checking ==="
cd "$PROJECT_ROOT/frontend"
npx tsc --noEmit
