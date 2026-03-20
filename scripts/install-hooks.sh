#!/usr/bin/env bash
# Install git pre-commit hook that runs fast checks.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_FILE="$PROJECT_ROOT/.git/hooks/pre-commit"

echo "=== Installing Pre-commit Hook ==="

cat > "$HOOK_FILE" << 'HOOK'
#!/usr/bin/env bash
# Auto-generated pre-commit hook. Re-run scripts/install-hooks.sh
# to update.
set -euo pipefail

SCRIPT_DIR="$(git rev-parse --show-toplevel)/scripts"
FAILED=()

run() {
    echo ""
    if ! "$SCRIPT_DIR/$1" "${@:2}"; then
        FAILED+=("$1")
    fi
}

run format-python.sh
run format-frontend.sh
run lint-python.sh
run lint-frontend.sh
run typecheck-frontend.sh
run detect-secrets.sh --staged

if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo ""
    echo "Pre-commit checks FAILED:"
    for f in "${FAILED[@]}"; do
        echo "  - $f"
    done
    echo ""
    echo "Fix the issues above and try again."
    exit 1
fi
HOOK

chmod +x "$HOOK_FILE"

echo "Pre-commit hook installed at: $HOOK_FILE"
echo ""
echo "The following checks run on every commit:"
echo "  - Python formatting (black)"
echo "  - Frontend formatting (prettier)"
echo "  - Python linting (flake8 + pylint)"
echo "  - Frontend linting (eslint)"
echo "  - TypeScript type checking"
echo "  - Secret detection (gitleaks, if installed)"
