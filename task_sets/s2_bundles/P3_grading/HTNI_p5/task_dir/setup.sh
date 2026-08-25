#!/usr/bin/env bash
set -euo pipefail
WORKSPACE="$1"
REPORTS="$2"
RUN_ID="$3"

mkdir -p "$WORKSPACE/output" "$WORKSPACE/tests" "$REPORTS"

# Install dependencies if needed
if command -v pip3 &>/dev/null; then
    pip3 install flask pytest --quiet 2>/dev/null || true
fi
