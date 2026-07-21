#!/bin/bash
# Setup Pi defaults for Agent Dashboard
#
# Installs agent overrides and global AGENTS.md for
# proactive sub-agent delegation.
#
# The pi-task tool rename (task → Agent) is now handled
# natively via the PI_TASK_TOOL_NAME env var in the Pi
# profile (pi.yaml), so no sed patch is needed.
#
# Run after:
#   - Fresh Pi extension installation
#   - pi-task upgrades (pi install npm:@heyhuynhgiabuu/pi-task)
#
# Usage:
#   ./agent/pi-defaults/setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PI_DIR="${HOME}/.pi/agent"

echo "=== Pi Defaults Setup ==="

# 1. Copy agent overrides
echo "Installing agent overrides to ~/.pi/agents/ ..."
mkdir -p "${HOME}/.pi/agents"
cp -r "${SCRIPT_DIR}/agents/"*.md "${HOME}/.pi/agents/"
echo "  ✓ Copied explore, scout, general, reviewer"

# 2. Install global AGENTS.md
echo "Installing global AGENTS.md to ${PI_DIR}/ ..."
mkdir -p "${PI_DIR}"
cp "${SCRIPT_DIR}/AGENTS.md" "${PI_DIR}/AGENTS.md"
echo "  ✓ Installed task delegation guidance"

echo ""
echo "Done. Restart Pi or run /reload to apply changes."
echo ""
echo "Note: pi-task tool rename (task → Agent) is handled"
echo "by the PI_TASK_TOOL_NAME env var in the Pi profile."
echo "Requires pi-task >= 0.3.5."
