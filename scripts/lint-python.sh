#!/usr/bin/env bash
# Run Python linting with flake8 and pylint.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Python Linting (flake8) ==="
cd "$PROJECT_ROOT"
flake8 backend/ agent/

echo "=== Python Linting (pylint) ==="
pylint backend/app/ agent/host_daemon.py
