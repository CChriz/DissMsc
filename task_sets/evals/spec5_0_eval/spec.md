# SPEC5: Worker Service Configuration System — Full Specification

## Overview

Implement a configuration management system for the Worker Service application.
The system must load configuration from multiple sources, validate all values
against the schema, apply correct defaults, and support type coercion.

## Configuration Schema

| Key | Type | Default | Env Var | Validation | Description |
|-----|------|---------|---------|------------|-------------|
| `queue_url` | `string` | "redis://localhost:6379/0" | `CELERY_QUEUE_URL` | non-empty string | URL of the message queue |
| `concurrency` | `int` | 3 | `CELERY_CONCURRENCY` | int in range [1, 32] | Number of concurrent workers; must be 1-32 |
| `max_retries` | `int` | 8 | `CELERY_MAX_RETRIES` | int in range [0, 20] | Maximum retry attempts per job; must be 0-20 |
| `retry_backoff_seconds` | `int` | 1 | `CELERY_RETRY_BACKOFF` | int in range [1, 300] | Seconds to wait between retries; must be 1-300 |
| `job_timeout` | `int` | 300 | `CELERY_JOB_TIMEOUT` | int in range [1, 3600] | Job execution timeout in seconds; must be 1-3600 |
| `log_level` | `enum` | "INFO" | `CELERY_LOG_LEVEL` | one of ['DEBUG', 'INFO', 'WARN'] | Logging verbosity; one of ['DEBUG', 'INFO', 'WARN'] |
| `dead_letter_queue` | `bool` | true | `CELERY_DEAD_LETTER` | bool | Route failed jobs to dead letter queue |
| `heartbeat_interval` | `int` | 60 | `CELERY_HEARTBEAT` | int in range [5, 300] | Worker heartbeat interval seconds; must be 5-300 |
| `prefetch_count` | `int` | 10 | `CELERY_PREFETCH` | int in range [1, 100] | Number of messages to prefetch; must be 1-100 |
| `ack_on_failure` | `bool` | false | `CELERY_ACK_ON_FAILURE` | bool | Acknowledge message even on job failure |
| `metrics_enabled` | `bool` | true | `CELERY_METRICS` | bool | Enable Prometheus metrics |

## Validation Rules (EXACT — must be implemented precisely)

- `queue_url`: must be a non-empty string
- `concurrency`: must be in range [1, 32] (inclusive)
- `max_retries`: must be in range [0, 20] (inclusive)
- `retry_backoff_seconds`: must be in range [1, 300] (inclusive)
- `job_timeout`: must be in range [1, 3600] (inclusive)
- `log_level`: must be one of ['DEBUG', 'INFO', 'WARN'] (case-sensitive)
- `dead_letter_queue`: accepts true/false (case-insensitive), 1/0, yes/no, on/off as string inputs
- `heartbeat_interval`: must be in range [5, 300] (inclusive)
- `prefetch_count`: must be in range [1, 100] (inclusive)
- `ack_on_failure`: accepts true/false (case-insensitive), 1/0, yes/no, on/off as string inputs
- `metrics_enabled`: accepts true/false (case-insensitive), 1/0, yes/no, on/off as string inputs

### Type Coercion

When loading from environment variables or config files, string values must be
coerced to the correct type:
- `int`: parse as integer; raise `ConfigValidationError` if not parseable
- `float`: parse as float; raise `ConfigValidationError` if not parseable
- `bool`: accept `true`/`false` (case-insensitive), `1`/`0`, `yes`/`no`, `on`/`off`;
  raise `ConfigValidationError` for any other string
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
| `CELERY_QUEUE_URL` | `queue_url` | `string` |
| `CELERY_CONCURRENCY` | `concurrency` | `int` |
| `CELERY_MAX_RETRIES` | `max_retries` | `int` |
| `CELERY_RETRY_BACKOFF` | `retry_backoff_seconds` | `int` |
| `CELERY_JOB_TIMEOUT` | `job_timeout` | `int` |
| `CELERY_LOG_LEVEL` | `log_level` | `enum` |
| `CELERY_DEAD_LETTER` | `dead_letter_queue` | `bool` |
| `CELERY_HEARTBEAT` | `heartbeat_interval` | `int` |
| `CELERY_PREFETCH` | `prefetch_count` | `int` |
| `CELERY_ACK_ON_FAILURE` | `ack_on_failure` | `bool` |
| `CELERY_METRICS` | `metrics_enabled` | `bool` |

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
