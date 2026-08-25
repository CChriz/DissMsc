# MULTI5: CI/CD Pipeline Repair

## Goal
Fix a broken CI/CD pipeline that has 3 failing stages: lint, test, and deploy.
Each stage uses different tools and languages, and each has a distinct root cause.

## Requirements
1. Fix the lint stage: the pylint configuration causes false positives that block the pipeline
2. Fix the test stage: pytest fixtures have incorrect scope causing resource exhaustion
3. Fix the deploy stage: the Dockerfile has path and build argument errors
4. All 3 stages must pass when run individually via their scripts
5. The `pipeline.yaml` must remain syntactically valid
6. Do NOT change the application source code (`app/`) — only fix pipeline tooling

## Supporting Documents
- `pipeline.yaml` — CI/CD pipeline configuration (describes stage order and commands)
- `scripts/lint.sh` — Lint stage script (runs pylint)
- `scripts/test.sh` — Test stage script (runs pytest)
- `scripts/deploy.sh` — Deploy stage script (builds Docker image)
- `.pylintrc` — Pylint configuration (has wrong max-line-length)
- `tests/conftest.py` — Pytest fixtures (wrong fixture scope)
- `Dockerfile` — Container build definition (wrong COPY path, missing build arg)
- `PIPELINE_DOCS.md` — Documents expected pipeline behavior

## The 3 Bugs (find them yourself)
Each stage fails for a different reason. Read the pipeline docs, scripts, and
configuration files to identify and fix each root cause.

## Important
Do NOT modify files under `app/`. Only fix pipeline configuration and tooling files.
