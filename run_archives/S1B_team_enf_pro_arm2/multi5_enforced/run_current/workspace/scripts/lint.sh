#!/usr/bin/env bash
set -euo pipefail
echo "Running pylint for webapp..."
python3 -m pylint --rcfile=.pylintrc app/
echo "Lint passed."
