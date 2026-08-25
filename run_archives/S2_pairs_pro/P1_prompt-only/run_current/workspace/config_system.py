"""
Configuration system for the Worker Service.

Implements a complete config management system with:
- 11 config keys with types, defaults, env vars, and validation rules
- Type coercion (int, float, bool, enum, string)
- Priority cascade: cli_args > env_vars > config_file > defaults
- Validation via ConfigValidationError
"""

import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


_SCHEMA: dict[str, dict] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env_var": "CELERY_QUEUE_URL",
        "validation": "non-empty",
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env_var": "CELERY_CONCURRENCY",
        "validation": {"min": 1, "max": 32},
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env_var": "CELERY_MAX_RETRIES",
        "validation": {"min": 0, "max": 20},
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env_var": "CELERY_RETRY_BACKOFF",
        "validation": {"min": 1, "max": 300},
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env_var": "CELERY_JOB_TIMEOUT",
        "validation": {"min": 1, "max": 3600},
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env_var": "CELERY_LOG_LEVEL",
        "validation": {"allowed": ["DEBUG", "INFO", "WARN"]},
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_DEAD_LETTER",
        "validation": "bool",
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env_var": "CELERY_HEARTBEAT",
        "validation": {"min": 5, "max": 300},
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env_var": "CELERY_PREFETCH",
        "validation": {"min": 1, "max": 100},
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env_var": "CELERY_ACK_ON_FAILURE",
        "validation": "bool",
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_METRICS",
        "validation": "bool",
    },
}


def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value for the given config key.

    Performs type coercion first, then applies validation rules.
    Raises ConfigValidationError on failure.
    """
    # Look up key in schema; return value unchanged if key not in schema
    if key not in _SCHEMA:
        return value

    spec = _SCHEMA[key]
    val_type = spec["type"]
    validation = spec.get("validation")

    # --- Type coercion ---
    coerced = _coerce_type(key, value, val_type)

    # --- Validation ---
    _apply_validation(key, coerced, val_type, validation)

    return coerced


def _coerce_type(key: str, value: Any, val_type: str) -> Any:
    """Coerce value to the expected type. Raises ConfigValidationError on failure."""

    if val_type == "int":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                raise ConfigValidationError(
                    f"Invalid int for {key!r}: {value!r}"
                )
        raise ConfigValidationError(f"Invalid int for {key!r}: {value!r}")

    elif val_type == "float":
        if isinstance(value, float):
            return value
        if isinstance(value, (int, str)):
            try:
                return float(value)
            except (ValueError, TypeError):
                raise ConfigValidationError(
                    f"Invalid float for {key!r}: {value!r}"
                )
        raise ConfigValidationError(f"Invalid float for {key!r}: {value!r}")

    elif val_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
            raise ConfigValidationError(
                f"Invalid bool for {key!r}: {value!r}"
            )
        if isinstance(value, int) and not isinstance(value, bool):
            if value == 1:
                return True
            if value == 0:
                return False
            raise ConfigValidationError(
                f"Invalid bool for {key!r}: {value!r}"
            )
        raise ConfigValidationError(f"Invalid bool for {key!r}: {value!r}")

    elif val_type == "enum":
        coerced = str(value)
        return coerced

    elif val_type == "string":
        return str(value)

    else:
        raise ConfigValidationError(f"Unknown type {val_type!r} for {key!r}")


def _apply_validation(
    key: str, value: Any, val_type: str, validation: Any
) -> None:
    """Apply validation rules to a coerced value. Raises ConfigValidationError."""

    # non-empty validation for strings
    if validation == "non-empty":
        if not value:
            raise ConfigValidationError(
                f"Invalid value for {key!r}: {value!r}"
            )
        return

    # range validation: {"min": X, "max": Y}
    if isinstance(validation, dict) and "min" in validation and "max" in validation:
        if not (validation["min"] <= value <= validation["max"]):
            raise ConfigValidationError(
                f"Invalid value for {key!r}: {value!r}"
            )
        return

    # allowed list validation for enum
    if isinstance(validation, dict) and "allowed" in validation:
        if value not in validation["allowed"]:
            raise ConfigValidationError(
                f"Invalid value for {key!r}: {value!r}"
            )
        return

    # "bool" validation: no additional checks needed beyond type coercion
    if validation == "bool":
        return


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    Args:
        config_file: Path to a JSON config file (optional).
        env_vars: Dict of environment variables (defaults to os.environ).
        cli_args: Dict of CLI arguments (optional).

    Returns:
        A dict with all 11 config keys, validated and type-coerced.
    """
    # Step 1 — Start from defaults
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2 — Config file (lowest priority source)
    if config_file is not None:
        with open(config_file, "r") as f:
            file_data = json.load(f)
        for key, value in file_data.items():
            if key in _SCHEMA:
                result[key] = validate_value(key, value)
            # unknown keys are silently ignored

    # Step 3 — Environment variables
    if env_vars is None:
        env_vars = os.environ
    for key, spec in _SCHEMA.items():
        env_var_name = spec["env_var"]
        if env_var_name in env_vars and env_vars[env_var_name] is not None:
            result[key] = validate_value(key, env_vars[env_var_name])

    # Step 4 — CLI args (highest priority)
    if cli_args is not None:
        for key, value in cli_args.items():
            if key in _SCHEMA and value is not None:
                result[key] = validate_value(key, value)
            # unknown keys are silently ignored

    return result


def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    return _SCHEMA
