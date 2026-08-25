# Combined task: P9

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: spec5  (spec, LB90)
====================================================================

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



====================================================================
## Subtask 2: lh5  (lh, LB90)
====================================================================

# LH5: Data Migration

## Goal
Execute a complete 6-step data migration for a IoT sensor telemetry system.
Source data is in `data/old_format/` (csv format).
Target is `data/new_format/` (JSONL format).

## Source Data
- `data/old_format/sensor_readings.csv`: **60 records** (primary table)
- `data/old_format/devices.csv`: **26 records** (reference table)

## Migration Steps (execute in strict order)

   1. **backup**: Create a backup of all source data before any changes
   2. **transform_format**: Convert records from old format to new target format
   3. **validate_checksums**: Verify data integrity via SHA-256 checksums of every record
   4. **load_new_store**: Load transformed records into the new data store
   5. **verify_counts**: Confirm row counts match between source and destination
   6. **update_references**: Rewrite foreign-key references to use new primary keys

## Validation Checkpoints

After **transform_format**:
- `data/transformed/` must contain JSONL files for both tables.
- Row count in `data/transformed/sensor_readings.jsonl` must equal `60`.

After **validate_checksums**:
- `checksums.json` must exist with keys `"source"` and `"transformed"`.
- Each entry must be a valid 64-character hex SHA-256 string.

After **load_new_store**:
- `data/new_format/sensor_readings.jsonl` must exist.
- Row count must equal `60`.
- `data/new_format/devices.jsonl` must exist.

After **verify_counts**:
- `verification_report.json` must exist.
- `counts_match` must be `true`.
- `source_count` must equal `dest_count` must equal `60`.

After **update_references**:
- Every `device_id` in `data/new_format/sensor_readings.jsonl` must exist in `data/new_format/devices.jsonl`.
- No orphaned `device_id` values are permitted.

## Rollback Triggers

If any step fails (returns False or raises an exception), the migration must:
1. Immediately stop execution of further steps.
2. Execute rollback for all successfully completed steps **in reverse order**.

Rollback actions per step:
   - Rollback of `backup`: Remove incomplete backup directory
   - Rollback of `transform_format`: Delete all files in data/transformed/
   - Rollback of `validate_checksums`: Clear checksum manifest (checksums.json)
   - Rollback of `load_new_store`: Truncate data/new_format/ directory
   - Rollback of `verify_counts`: Remove verification report
   - Rollback of `update_references`: Restore original reference mapping from backup

## Required Output Files

- `migration_log.jsonl`: Every step start/complete/fail/rollback event.
- `migration_report.json`: `{"status": "success", "steps_completed": [...], "total_steps": 6, "ts": "<iso>"}`
- `checksums.json`: SHA-256 checksums of source and transformed files.
- `verification_report.json`: `{"source_count": 60, "dest_count": 60, "counts_match": true}`
- `data/backup/`: Copy of original source files.
- `data/new_format/sensor_readings.jsonl`: Migrated primary records.
- `data/new_format/devices.jsonl`: Migrated reference records.


## Deliverables
- Complete implementation of all TODO functions in `migrate.py`.
- Run `python migrate.py` to execute the migration.
- Run `python validate.py` — all checks must pass.
