#!/bin/bash
# Setup Pi defaults for Agent Dashboard
#
# Installs agent overrides, global AGENTS.md, and
# renames pi-task's tool from "task" to "Agent" for
# proactive sub-agent delegation.
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
PI_TASK_INDEX="${PI_DIR}/npm/node_modules/@heyhuynhgiabuu/pi-task/dist/index.js"

echo "=== Pi Defaults Setup ==="

# 1. Copy agent overrides
echo "Installing agent overrides to ${PI_DIR}/../../agents/ ..."
mkdir -p "${HOME}/.pi/agents"
cp -r "${SCRIPT_DIR}/agents/"*.md "${HOME}/.pi/agents/"
echo "  ✓ Copied explore, scout, general, reviewer"

# 2. Install global AGENTS.md
echo "Installing global AGENTS.md to ${PI_DIR}/ ..."
cp "${SCRIPT_DIR}/AGENTS.md" "${PI_DIR}/AGENTS.md"
echo "  ✓ Installed task delegation guidance"

# 3. Rename pi-task tool from "task" to "Agent"
if [ -f "${PI_TASK_INDEX}" ]; then
    if grep -q 'name: "task"' "${PI_TASK_INDEX}"; then
        sed -i 's/name: "task"/name: "Agent"/' "${PI_TASK_INDEX}"
        echo "  ✓ Renamed pi-task tool: task → Agent"
    elif grep -q 'name: "Agent"' "${PI_TASK_INDEX}"; then
        echo "  ✓ pi-task tool already named Agent"
    else
        echo "  ⚠ Could not find tool name in pi-task index.js"
    fi
else
    echo "  ⚠ pi-task not installed — skipping tool rename"
    echo "    Install with: pi install npm:@heyhuynhgiabuu/pi-task"
fi

echo ""
echo "Done. Restart Pi or run /reload to apply changes."
