# Combined task: P8

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: multi4  (multi, LTNI)
====================================================================

# MULTI4: Monorepo Dependency Fix (Brief)

Fix 3 dependency issues in a 5-package Python monorepo: a circular import between
`models` and `api`, a stale version pin in `utils`, and a moved function reference
in `worker`. The Planner has mapped the full dependency graph and identified each fix.

Follow the Planner's guidance precisely. Run `pytest tests/` to verify all imports resolve and versions are consistent.



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
