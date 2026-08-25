# SPEC5: Web Service Configuration System (Executor Brief)

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
