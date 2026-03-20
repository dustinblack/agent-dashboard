#!/usr/bin/env bash
# Run backend unit tests with pytest and coverage.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Backend Unit Tests (pytest + coverage) ==="
cd "$PROJECT_ROOT"
pytest backend/tests/test_main.py \
    --cov=backend/app \
    --cov-report=term-missing \
    --cov-report=html:coverage/backend \
    --cov-report=json:coverage/backend/coverage.json
