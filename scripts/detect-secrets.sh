#!/usr/bin/env bash
# Run secret detection with gitleaks.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Secret Detection (gitleaks) ==="

if ! command -v gitleaks &>/dev/null; then
    echo "WARNING: gitleaks not installed, skipping."
    echo "Install: https://github.com/gitleaks/gitleaks#installing"
    exit 0
fi

cd "$PROJECT_ROOT"

# In pre-commit mode, only scan staged changes.
# In CI mode, scan the full repository.
if [[ "${1:-}" == "--staged" ]]; then
    gitleaks protect --staged
else
    gitleaks detect --source .
fi
