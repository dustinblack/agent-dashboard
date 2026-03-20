#!/usr/bin/env bash
# Build the frontend with vite.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Frontend Build (vite) ==="
cd "$PROJECT_ROOT/frontend"
npm run build
