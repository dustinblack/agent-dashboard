#!/usr/bin/env bash
# Check Python formatting with black.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Python Formatting (black) ==="
cd "$PROJECT_ROOT"
black --check --diff backend/ agent/
