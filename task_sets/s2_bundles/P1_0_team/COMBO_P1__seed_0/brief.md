# Combined task: P1

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: cr4  (cr, LB90)
====================================================================

# CR4: API Design Fix (Brief)

## Your Task
The REST API in `app.py` was flagged during code review for multiple
API design violations.

Fix all the violations so the API conforms to the team's REST API design guidelines.

## What You Know
- The API is in `app.py` (Flask/Python).
- The code review found issues with: HTTP methods, route naming, pagination,
  status codes, API versioning, and error responses.
- `tests/test_api.py` must pass without any modification after your fixes.
- Do NOT modify `tests/test_api.py`.
- Install dependencies with `pip install -r requirements.txt` before running tests.

## What the Planner Has
The Planner has the full API review report listing every violation with exact
locations and the required fixes. Follow the Planner's instructions precisely.

## Running Tests
```bash
pip install -r requirements.txt
pytest tests/test_api.py -v
```



====================================================================
## Subtask 2: spec5  (spec, LB90)
====================================================================

# SPEC5: Worker Service Configuration System (Executor Brief)

The application needs a configuration management system. Implement it.

## Workspace

- `config_skeleton.py` — skeleton with class/function stubs and TODOs
- `config_schema.json` — partial schema (incomplete — the Planner has the full spec)

## What to Implement

Create `config_system.py` that implements:

1. `ConfigValidationError` — exception class
2. `load_config(config_file, env_vars, cli_args)` — loads config from all sources
3. `get_schema()` — returns the full schema dict
4. `validate_value(key, value)` — validates and coerces a single value

The Planner has the full specification including:
- Complete config schema with all keys, types, defaults, and validation rules
- Priority cascade order (CLI > env vars > config file > defaults)
- Exact type coercion rules for booleans, ints, floats
- Exact error types and messages

## Testing

```bash
python3 -c "from config_system import load_config; cfg = load_config(); print(cfg)"
```
