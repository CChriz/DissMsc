# Pipeline Documentation for webapp

## Overview
The CI/CD pipeline has 3 stages that run in sequence: lint, test, deploy.

## Stage 1: Lint
- Runs pylint on all Python files under `app/`
- Uses `.pylintrc` for configuration
- **Expected**: max-line-length should be 120 (standard for this project)
- Lines up to 120 characters are acceptable

## Stage 2: Test
- Runs pytest on all tests under `tests/`
- The database fixture in `conftest.py` must use `scope="session"` to prevent
  connection exhaustion — the postgresql test instance has a connection limit
- All tests should pass with a single database connection shared across the session

## Stage 3: Deploy
- Builds a Docker image using the `Dockerfile`
- Requires `APP_VERSION` build argument (declared as `ARG` in Dockerfile)
- The application code lives in `app/` directory (must be copied correctly)
- Image is tagged with the version and pushed to the registry

## Troubleshooting
- If lint fails with line-length errors, check `.pylintrc` max-line-length
- If tests fail with connection errors, check conftest.py fixture scope
- If docker build fails, check COPY paths and ARG declarations
