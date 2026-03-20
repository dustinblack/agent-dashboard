#!/usr/bin/env bash
# Run frontend security audit with npm audit.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Frontend Security (npm audit) ==="
cd "$PROJECT_ROOT/frontend"
npm audit --audit-level=high
