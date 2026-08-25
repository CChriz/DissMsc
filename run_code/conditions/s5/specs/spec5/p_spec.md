# SPEC5: Web Service Configuration System — Full Specification

## Overview

Implement a configuration management system for the Web Service application.
The system must load configuration from multiple sources, validate all values
against the schema, apply correct defaults, and support type coercion.

## Configuration Schema

| Key | Type | Default | Env Var | Validation | Description |
|-----|------|---------|---------|------------|-------------|
| `host` | `string` | "0.0.0.0" | `WEB_HOST` | non-empty string | Hostname or IP address to bind |
| `port` | `int` | 6155 | `WEB_PORT` | int | TCP port to listen on |
| `log_level` | `enum` | "WARN" | `WEB_LOG_LEVEL` | one of the allowed levels | Logging verbosity |
| `request_timeout` | `int` | 120 | `WEB_REQUEST_TIMEOUT` | int | Request timeout in seconds |
| `max_connections` | `int` | 348 | `WEB_MAX_CONNECTIONS` | int | Maximum concurrent connections |
| `debug_mode` | `bool` | false | `WEB_DEBUG` | bool | Enable debug mode |
| `static_dir` | `string` | "./static" | `WEB_STATIC_DIR` | non-empty string | Path to static files directory |
| `cors_origins` | `string` | "*" | `WEB_CORS_ORIGINS` | string (any) | Allowed CORS origins, comma-separated |
| `keep_alive_timeout` | `int` | 10 | `WEB_KEEP_ALIVE_TIMEOUT` | int | Keep-alive timeout seconds |
| `ssl_enabled` | `bool` | false | `WEB_SSL_ENABLED` | bool | Enable SSL/TLS |

## Validation Rules

- `host`: must be a non-empty string
- `log_level`: must be one of the allowed logging levels
- `static_dir`: must be a non-empty string
- Integer keys must parse as integers; boolean keys must parse as booleans.

### Type Coercion

When loading from environment variables or config files, string values must be
coerced to the correct type:
- `int`: parse as integer; raise `ConfigValidationError` if not parseable
- `float`: parse as float; raise `ConfigValidationError` if not parseable
- `bool`: parse common boolean string forms
- `enum`: validate the coerced string against `allowed` values
- `string`: use as-is

## Priority Cascade (EXACT order — highest priority first)

1. **CLI arguments** (passed programmatically as a dict to `load_config()`)
2. **Environment variables** (read from `os.environ`)
3. **Config file** (JSON file path passed to `load_config()`)
4. **Built-in defaults** (defined in the schema)

Later sources fill in keys not provided by higher-priority sources.
A key set to the string `""` in a lower-priority source is still overridden
by a non-None value from a higher-priority source.

## Error Handling

All validation failures must raise `ConfigValidationError` (a subclass of `ValueError`)
with a descriptive message. The error must include the key name and the invalid value.

## API Contract

```python
# config_system.py — you must implement this file

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass

def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,   # defaults to os.environ if None
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources in priority order.

    Args:
        config_file: Path to a JSON config file (optional).
        env_vars: Dict of environment variables (defaults to os.environ).
        cli_args: Dict of CLI arguments — highest priority.

    Returns:
        A dict with all config keys populated, validated, and type-coerced.

    Raises:
        ConfigValidationError: If any value fails validation.
        FileNotFoundError: If config_file is specified but does not exist.
    """
    ...

def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    ...

def validate_value(key: str, value) -> object:
    """
    Validate and coerce a single value against the schema for `key`.

    Returns the coerced value.
    Raises ConfigValidationError if invalid.
    """
    ...
```

## Environment Variable Mapping

| Environment Variable | Config Key | Type |
|----------------------|------------|------|
| `WEB_HOST` | `host` | `string` |
| `WEB_PORT` | `port` | `int` |
| `WEB_LOG_LEVEL` | `log_level` | `enum` |
| `WEB_REQUEST_TIMEOUT` | `request_timeout` | `int` |
| `WEB_MAX_CONNECTIONS` | `max_connections` | `int` |
| `WEB_DEBUG` | `debug_mode` | `bool` |
| `WEB_STATIC_DIR` | `static_dir` | `string` |
| `WEB_CORS_ORIGINS` | `cors_origins` | `string` |
| `WEB_KEEP_ALIVE_TIMEOUT` | `keep_alive_timeout` | `int` |
| `WEB_SSL_ENABLED` | `ssl_enabled` | `bool` |

## Config File Format

The config file is a JSON object with config keys as fields:
```json
{
  "key_name": value,
  ...
}
```
Unknown keys in the config file are ignored (not an error).

## Notes

- The schema is available at runtime via `get_schema()`; do not hard-code it
  separately from the implementation.
- The `config_schema.json` in the workspace contains a **partial** schema
  (only some keys). The full schema is defined above — use the spec, not the
  JSON file, as the authoritative source.
- All config keys defined in the schema must be present in the returned dict,
  even if no source provides a value (use the default).
