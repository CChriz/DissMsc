#!/usr/bin/env bash
set -euo pipefail
echo "Running pytest for webapp..."
python3 -m pytest tests/ -v
echo "Tests passed."
