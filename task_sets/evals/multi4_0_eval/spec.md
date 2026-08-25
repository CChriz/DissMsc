# MULTI4: Monorepo Dependency Fix

## Goal
Fix 3 dependency issues in a Python monorepo with 5 packages. The issues include
a circular import, a stale version pin, and a moved function reference. All 3 must
be fixed in a coordinated way to restore a valid dependency graph.

## Requirements
1. **Break circular dependency**: The `models` package imported a helper from `api`, creating a cycle (`models` -> `api` -> `core` -> `models`). Move the shared helper to `utils` (where it belongs) and update all imports.
2. **Update stale version pin**: The `utils` package pins `core==1.0` but uses features added in `core` v1.2. Update the pin to `core>=1.2`.
3. **Fix moved function import**: The `worker` package imports `process_item()` from `core`, but that function was moved to `utils` in v1.2. Update the import in `worker` to reference `utils`.
4. After fixes, no package should have a circular dependency.
5. All version constraints must be satisfiable simultaneously.
6. All tests in `tests/` must pass.

## Supporting Documents
- `core/` — Core package (v1.2.0): base classes and interfaces
- `models/` — Models package (v1.1.0): data models, incorrectly imports from `api`
- `api/` — API package (v1.0.0): REST endpoints, depends on `core` and `models`
- `worker/` — Worker package (v1.0.0): background jobs, imports moved function from `core`
- `utils/` — Utils package (v1.1.0): shared utilities, has stale version pin on `core`
- `tests/test_imports.py` — Tests for import validity and cycle detection
- `tests/test_versions.py` — Tests for version constraint consistency
- `CHANGELOG.md` — Records when functions were moved between packages

## Background

### Monorepo Dependency Management

In a Python monorepo, packages often share types and utilities. Over time, three
common issues arise:

1. **Circular imports**: Package A imports from B, which imports from C, which imports
   from A. Python cannot resolve this at import time.
2. **Stale version pins**: When a shared package evolves, downstream packages may pin
   old versions that lack required features.
3. **Moved functions**: Refactoring moves functions between packages, but not all
   callers are updated.

### The 3 Bugs

| Package | Bug | Root Cause |
|---------|-----|------------|
| `models` | Circular import | `models/helpers.py` imports `format_response` from `api.formatters` |
| `utils` | Stale version pin | `setup.cfg` requires `core==1.0` but uses `core.BaseProcessor` (added in 1.2) |
| `worker` | Moved function | `worker/tasks.py` imports `process_item` from `core.processing`, but it moved to `utils.processing` |

### Fix Strategy

1. Move `format_response` from `api/formatters.py` to `utils/formatters.py`. Update
   `models/helpers.py` to import from `utils` instead of `api`. Update `api/formatters.py`
   to re-export from `utils` for backward compatibility.
2. In `utils/setup.cfg`, change `core==1.0` to `core>=1.2`.
3. In `worker/tasks.py`, change `from core.processing import process_item` to
   `from utils.processing import process_item`.

## Hidden Complexity
- Simply deleting the circular import in `models` without moving the function would
  break `models`' functionality.
- The version pin in `utils` must be `>=1.2`, not `>=1.0` — otherwise the stale
  import of `BaseProcessor` would fail at runtime on older versions of `core`.
- The `api/formatters.py` re-export ensures backward compatibility for any external
  consumer that already imports from `api.formatters`.
