"""
Configuration system for Worker Service.
Implements the full config management with priority cascade:
    CLI args > env vars > config file > defaults
"""
import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""

    def __init__(self, key: str, value: Any):
        self.key = key
        self.value = value
        super().__init__(f"Invalid value for '{key}': {value!r}")


_SCHEMA: dict[str, dict] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env_var": "CELERY_QUEUE_URL",
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env_var": "CELERY_CONCURRENCY",
        "min": 1,
        "max": 32,
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env_var": "CELERY_MAX_RETRIES",
        "min": 0,
        "max": 20,
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env_var": "CELERY_RETRY_BACKOFF",
        "min": 1,
        "max": 300,
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env_var": "CELERY_JOB_TIMEOUT",
        "min": 1,
        "max": 3600,
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env_var": "CELERY_LOG_LEVEL",
        "allowed": ["DEBUG", "INFO", "WARN"],
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_DEAD_LETTER",
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env_var": "CELERY_HEARTBEAT",
        "min": 5,
        "max": 300,
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env_var": "CELERY_PREFETCH",
        "min": 1,
        "max": 100,
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env_var": "CELERY_ACK_ON_FAILURE",
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_METRICS",
    },
}


def get_schema() -> dict:
    """Return a copy of the config schema."""
    return dict(_SCHEMA)


def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value for the given config key.

    Type coercion rules:
      - string: non-empty string; empty string raises ConfigValidationError
      - int: int(v) conversion; validates [min, max] range
      - float: float(v) conversion (reserved; no current schema uses float)
      - bool: accepts bool, int 0/1, or str in true/false/1/0/yes/no/on/off
      - enum: value must be in allowed list (case-sensitive)

    Raises ConfigValidationError on any failure.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(key, value)

    spec = _SCHEMA[key]
    type_name = spec["type"]

    if type_name == "string":
        if not isinstance(value, str) or value == "":
            raise ConfigValidationError(key, value)
        return value

    elif type_name == "int":
        try:
            coerced = int(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(key, value)
        if "min" in spec and coerced < spec["min"]:
            raise ConfigValidationError(key, value)
        if "max" in spec and coerced > spec["max"]:
            raise ConfigValidationError(key, value)
        return coerced

    elif type_name == "float":
        try:
            coerced = float(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(key, value)
        return coerced

    elif type_name == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
        raise ConfigValidationError(key, value)

    elif type_name == "enum":
        allowed = spec.get("allowed", [])
        if value not in allowed:
            raise ConfigValidationError(key, value)
        return value

    else:
        raise ConfigValidationError(key, value)


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    Args:
        config_file: path to JSON config file (optional)
        env_vars: environment variables dict (defaults to os.environ)
        cli_args: CLI arguments dict (optional)

    Returns:
        Fully validated and coerced config dict.

    Raises:
        FileNotFoundError: if config_file path does not exist
        ConfigValidationError: if any value fails validation
    """
    # Step 1: Initialize from defaults
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2: Overlay from config file
    if config_file is not None:
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        for key, value in file_data.items():
            if key in _SCHEMA:
                result[key] = value

    # Step 3: Overlay from environment variables
    if env_vars is None:
        env_vars = dict(os.environ)
    for key, spec in _SCHEMA.items():
        env_name = spec.get("env_var")
        if env_name and env_name in env_vars:
            result[key] = env_vars[env_name]

    # Step 4: Overlay from CLI args (highest priority)
    if cli_args is not None:
        for key, value in cli_args.items():
            if key in _SCHEMA:
                result[key] = value

    # Step 5: Validate and coerce all values
    final: dict[str, Any] = {}
    for key in _SCHEMA:
        final[key] = validate_value(key, result[key])

    return final
