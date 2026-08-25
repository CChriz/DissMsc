# Combined task: P9

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: spec5  (spec, LB90)
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



====================================================================
## Subtask 2: lh5  (lh, LB90)
====================================================================

# LH5: Data Migration (Brief)

Data needs to be migrated to the new format. Execute the migration.

- Source: `data/old_format/` (csv)
- Target: `data/new_format/` (jsonl)
- Domain: IoT sensor telemetry

Run: `python migrate.py`
Validate: `python validate.py`

The Planner has the full 6-step migration plan with validation checkpoints and rollback triggers.
