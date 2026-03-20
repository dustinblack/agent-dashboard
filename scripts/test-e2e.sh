#!/usr/bin/env bash
# Run E2E socket tests with pytest.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== E2E Tests (pytest) ==="
cd "$PROJECT_ROOT"
pytest backend/tests/test_e2e_socket.py
