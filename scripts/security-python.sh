#!/usr/bin/env bash
# Run Python security scanning with bandit.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Python Security (bandit) ==="
cd "$PROJECT_ROOT"
bandit -r backend/app/ agent/ -ll
