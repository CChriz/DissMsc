"""
Worker Service configuration system.

Implements the SPEC5 configuration subsystem:
- ConfigValidationError exception class
- load_config() with priority cascade: cli_args > env_vars > config_file > defaults
- get_schema() returning the full schema
- validate_value() for type coercion and validation

Authoritative source: spec.md Subtask 2. The partial config_schema.json in the
workspace belongs to a different domain and is intentionally NOT used here.
"""

import copy
import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# Full schema (single source of truth, defined once at module level).
_SCHEMA: dict[str, dict] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env": "CELERY_QUEUE_URL",
        "non_empty": True,
        "description": "URL of the message queue",
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env": "CELERY_CONCURRENCY",
        "min": 1,
        "max": 32,
        "description": "Number of concurrent worker processes",
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env": "CELERY_MAX_RETRIES",
        "min": 0,
        "max": 20,
        "description": "Maximum number of retries before giving up",
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env": "CELERY_RETRY_BACKOFF",
        "min": 1,
        "max": 300,
        "description": "Backoff delay between retries, in seconds",
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env": "CELERY_JOB_TIMEOUT",
        "min": 1,
        "max": 3600,
        "description": "Job execution timeout, in seconds",
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env": "CELERY_LOG_LEVEL",
        "allowed": ["DEBUG", "INFO", "WARN"],
        "description": "Logging verbosity level",
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env": "CELERY_DEAD_LETTER",
        "description": "Whether to route failed jobs to a dead-letter queue",
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env": "CELERY_HEARTBEAT",
        "min": 5,
        "max": 300,
        "description": "Heartbeat interval, in seconds",
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env": "CELERY_PREFETCH",
        "min": 1,
        "max": 100,
        "description": "Number of messages to prefetch",
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env": "CELERY_ACK_ON_FAILURE",
        "description": "Whether to acknowledge messages on failure",
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env": "CELERY_METRICS",
        "description": "Whether to enable metrics collection",
    },
}


def get_schema() -> dict:
    """Return a deep copy of the config schema."""
    return copy.deepcopy(_SCHEMA)


def _error(key: str, value: Any, reason: str) -> ConfigValidationError:
    """Build a ConfigValidationError with the required key/value/reason content."""
    return ConfigValidationError(
        f"Config key '{key}' has invalid value {value!r}: {reason}"
    )


def _check_range(key: str, original: Any, coerced: Any, spec: dict) -> None:
    """Raise ConfigValidationError if ``coerced`` is outside [min, max]."""
    if "min" in spec and coerced < spec["min"]:
        raise _error(
            key, original, f"must be in range [{spec['min']}, {spec['max']}]"
        )
    if "max" in spec and coerced > spec["max"]:
        raise _error(
            key, original, f"must be in range [{spec['min']}, {spec['max']}]"
        )


def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value for the given config key.

    Raises ConfigValidationError on failure; every error message contains the
    key name, the invalid value, and a short reason.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key '{key}'")

    spec = _SCHEMA[key]
    vtype = spec["type"]

    # --- string ---
    if vtype == "string":
        if not isinstance(value, str):
            raise _error(key, value, "expected string")
        if spec.get("non_empty") and value == "":
            raise _error(key, value, "must be non-empty string")
        return value

    # --- int ---
    if vtype == "int":
        # bool is a subclass of int; reject it first so True != 1.
        if isinstance(value, bool):
            raise _error(key, value, "expected integer")
        if isinstance(value, int):
            coerced = value
        elif isinstance(value, str):
            try:
                coerced = int(value)
            except ValueError:
                raise _error(key, value, "not a valid integer")
        else:
            # Reject floats (and everything else) rather than silently truncate.
            raise _error(key, value, "expected integer")
        _check_range(key, value, coerced, spec)
        return coerced

    # --- float (kept for completeness; schema currently has no float keys) ---
    if vtype == "float":
        if isinstance(value, bool):
            raise _error(key, value, "expected number")
        if isinstance(value, (int, float)):
            coerced = float(value)
        elif isinstance(value, str):
            try:
                coerced = float(value)
            except ValueError:
                raise _error(key, value, "not a valid number")
        else:
            raise _error(key, value, "expected number")
        _check_range(key, value, coerced, spec)
        return coerced

    # --- bool ---
    if vtype == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            norm = value.strip().lower()
            if norm in ("true", "1", "yes", "on"):
                return True
            if norm in ("false", "0", "no", "off"):
                return False
        raise _error(key, value, "expected boolean")

    # --- enum (case-sensitive) ---
    if vtype == "enum":
        allowed = spec.get("allowed", [])
        if not isinstance(value, str):
            raise _error(key, value, f"must be one of {allowed}")
        if value not in allowed:
            raise _error(key, value, f"must be one of {allowed}")
        return value

    raise _error(key, value, f"unknown type '{vtype}'")


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults.

    A value is considered "provided" by a source only when the key exists in
    that source AND the value is not None. Lower-priority values are overridden
    by higher-priority ones. All values are validated and coerced at the end.
    """
    schema = _SCHEMA

    # 1) Base layer: built-in defaults (ensures all keys are present).
    result: dict[str, Any] = {k: spec["default"] for k, spec in schema.items()}

    # 2) Config file (priority 3).
    if config_file is not None:
        with open(config_file, "r") as f:
            file_data = json.load(f)
        if isinstance(file_data, dict):
            for k, v in file_data.items():
                if k in schema and v is not None:
                    result[k] = v

    # 3) Environment variables (priority 2).
    if env_vars is None:
        env_vars = os.environ
    for k, spec in schema.items():
        env_name = spec["env"]
        if env_name in env_vars and env_vars[env_name] is not None:
            result[k] = env_vars[env_name]

    # 4) CLI args (priority 1, highest).
    if cli_args:
        for k, v in cli_args.items():
            if k in schema and v is not None:
                result[k] = v

    # 5) Final uniform validation + coercion over every schema key.
    return {k: validate_value(k, result[k]) for k in schema}
