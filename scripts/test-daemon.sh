#!/usr/bin/env bash
# Run host daemon unit tests with pytest and coverage.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Host Daemon Unit Tests (pytest + coverage) ==="
cd "$PROJECT_ROOT"
pytest agent/tests/ \
    --cov=agent \
    --cov-config=pyproject.toml \
    --cov-report=term-missing \
    --cov-report=html:coverage/daemon \
    --cov-report=json:coverage/daemon/coverage.json
