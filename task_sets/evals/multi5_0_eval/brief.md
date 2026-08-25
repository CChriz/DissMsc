# MULTI5: CI/CD Pipeline Repair (Brief)

Fix a 3-stage CI/CD pipeline (lint, test, deploy) where each stage fails for a different reason.

Fix only pipeline tooling files (`.pylintrc`, `tests/conftest.py`, `Dockerfile`, scripts).
Do NOT modify application source code under `app/`.

Run each stage script (`scripts/lint.sh`, `scripts/test.sh`, `scripts/deploy.sh`) to verify.
