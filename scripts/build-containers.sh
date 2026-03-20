#!/usr/bin/env bash
# Build all container images with podman.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Container Builds (podman) ==="
cd "$PROJECT_ROOT"

echo "--- Building backend container ---"
podman build -t agent-dashboard-backend \
    -f backend/Containerfile backend/

echo "--- Building frontend container ---"
podman build -t agent-dashboard-frontend \
    -f frontend/Containerfile frontend/

echo "--- Building agent daemon container ---"
podman build -t agent-dashboard-daemon \
    -f agent/Containerfile agent/
