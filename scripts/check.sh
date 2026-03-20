#!/usr/bin/env bash
# Runner script: orchestrates checks by category.
#
# Usage: ./scripts/check.sh [category...]
#
# Categories:
#   format     Run formatting checks (black, prettier)
#   lint       Run linting (flake8, pylint, eslint)
#   typecheck  Run TypeScript type checking
#   build      Run frontend build
#   test       Run backend unit tests with coverage
#   e2e        Run E2E tests
#   security   Run security scans (bandit, npm audit)
#   secrets    Run secret detection (gitleaks)
#   containers Build all container images
#   precommit  Run all pre-commit checks (fast)
#   ci         Run all CI checks
#   all        Run everything
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=()

run_script() {
    local name="$1"
    local script="$SCRIPT_DIR/$name"
    if [[ ! -x "$script" ]]; then
        echo "WARNING: $script not found or not executable"
        FAILED+=("$name")
        return
    fi
    if ! "$script"; then
        FAILED+=("$name")
    fi
}

run_category() {
    local category="$1"
    case "$category" in
        format)
            run_script format-python.sh
            run_script format-frontend.sh
            ;;
        lint)
            run_script lint-python.sh
            run_script lint-frontend.sh
            ;;
        typecheck)
            run_script typecheck-frontend.sh
            ;;
        build)
            run_script build-frontend.sh
            ;;
        test)
            run_script test-backend.sh
            ;;
        e2e)
            run_script test-e2e.sh
            ;;
        security)
            run_script security-python.sh
            run_script security-frontend.sh
            ;;
        secrets)
            run_script detect-secrets.sh
            ;;
        containers)
            run_script build-containers.sh
            ;;
        precommit)
            run_category format
            run_category lint
            run_category typecheck
            run_script detect-secrets.sh
            ;;
        ci)
            run_category format
            run_category lint
            run_category typecheck
            run_category build
            run_category test
            run_category security
            run_category secrets
            ;;
        all)
            run_category ci
            run_category e2e
            run_category containers
            ;;
        *)
            echo "Unknown category: $category"
            echo "Valid: format lint typecheck build test e2e" \
                 "security secrets containers precommit ci all"
            exit 1
            ;;
    esac
}

if [[ $# -eq 0 ]]; then
    echo "Usage: ./scripts/check.sh [category...]"
    echo ""
    echo "Categories: format lint typecheck build test e2e" \
         "security secrets containers precommit ci all"
    exit 0
fi

for category in "$@"; do
    run_category "$category"
done

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "=== FAILED CHECKS ==="
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    exit 1
fi

echo ""
echo "=== All checks passed ==="
