"""
Worker Service Configuration System — spec5 implementation.

Provides a configuration management system for the Celery Worker Service:
- 11-key schema with types, defaults, validation rules, and env var mappings
- Priority cascade: CLI args > env vars > config file > defaults
- Type coercion for int, float, bool, enum, and string
- ConfigValidationError for invalid values
"""

import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""

    pass


# ---------------------------------------------------------------------------
# Schema — all 11 Celery Worker Service configuration keys
# ---------------------------------------------------------------------------

SCHEMA: dict[str, dict] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env": "CELERY_QUEUE_URL",
        "validate": lambda v: isinstance(v, str) and len(v) > 0,
        "validate_msg": "must be a non-empty string",
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env": "CELERY_CONCURRENCY",
        "validate": lambda v: isinstance(v, int) and 1 <= v <= 32,
        "validate_msg": "must be an integer in range [1, 32]",
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env": "CELERY_MAX_RETRIES",
        "validate": lambda v: isinstance(v, int) and 0 <= v <= 20,
        "validate_msg": "must be an integer in range [0, 20]",
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env": "CELERY_RETRY_BACKOFF",
        "validate": lambda v: isinstance(v, int) and 1 <= v <= 300,
        "validate_msg": "must be an integer in range [1, 300]",
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env": "CELERY_JOB_TIMEOUT",
        "validate": lambda v: isinstance(v, int) and 1 <= v <= 3600,
        "validate_msg": "must be an integer in range [1, 3600]",
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env": "CELERY_LOG_LEVEL",
        "allowed": ["DEBUG", "INFO", "WARN"],
        "validate": lambda v: v in ["DEBUG", "INFO", "WARN"],
        "validate_msg": "must be one of ['DEBUG', 'INFO', 'WARN']",
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env": "CELERY_DEAD_LETTER",
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env": "CELERY_HEARTBEAT",
        "validate": lambda v: isinstance(v, int) and 5 <= v <= 300,
        "validate_msg": "must be an integer in range [5, 300]",
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env": "CELERY_PREFETCH",
        "validate": lambda v: isinstance(v, int) and 1 <= v <= 100,
        "validate_msg": "must be an integer in range [1, 100]",
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env": "CELERY_ACK_ON_FAILURE",
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env": "CELERY_METRICS",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_schema() -> dict:
    """Return the full configuration schema (key → spec dict)."""
    return SCHEMA


def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value for the given config key.

    Returns the coerced value.
    Raises ConfigValidationError if the key is unknown or the value is invalid.
    """
    schema = get_schema()

    if key not in schema:
        raise ConfigValidationError(
            f"Key '{key}': unknown configuration key (got: {value!r})"
        )

    spec = schema[key]
    coerced = _coerce_value(key, value, spec)

    # bool / string types have no extra range validation
    if spec["type"] in ("bool",):
        return coerced

    # Run the validate lambda if present
    if "validate" in spec and not spec["validate"](coerced):
        raise ConfigValidationError(
            f"Key '{key}': {spec['validate_msg']} (got: {coerced!r})"
        )

    return coerced


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources.

    Priority (highest first):
        1. CLI args
        2. Environment variables
        3. JSON config file
        4. Built-in defaults

    Returns a dict with all 11 keys, each coerced and validated.
    """
    schema = get_schema()

    if env_vars is None:
        env_vars = dict(os.environ)

    if cli_args is None:
        cli_args = {}

    # Step 1: start from defaults
    result: dict[str, Any] = {}
    for key, spec in schema.items():
        result[key] = spec["default"]

    # Step 2: overlay config_file (priority: file > defaults)
    if config_file is not None:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r") as f:
            file_data = json.load(f)
        for key in schema:
            if key in file_data:
                result[key] = file_data[key]
        # unknown keys in the config file are silently ignored

    # Step 3: overlay env vars (priority: env > file)
    for key, spec in schema.items():
        env_name = spec["env"]
        if env_name in env_vars:
            result[key] = env_vars[env_name]

    # Step 4: overlay CLI args (priority: CLI > env — highest)
    for key in schema:
        if key in cli_args and cli_args[key] is not None:
            result[key] = cli_args[key]

    # Step 5: coerce and validate every value
    final: dict[str, Any] = {}
    for key in schema:
        final[key] = validate_value(key, result[key])

    return final


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_value(key: str, raw_value: Any, spec: dict) -> Any:
    """Coerce a raw value (possibly a string from env vars) to the target type.

    Returns the coerced value.
    Raises ConfigValidationError on conversion failure.
    """
    target_type = spec["type"]

    if target_type == "string":
        return str(raw_value)

    elif target_type == "int":
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Key '{key}': must be a valid integer (got: {raw_value!r})"
            )

    elif target_type == "float":
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Key '{key}': must be a valid float (got: {raw_value!r})"
            )

    elif target_type == "bool":
        # Already a Python bool (from JSON file / CLI dict) — check first
        # because bool is a subclass of int in Python.
        if isinstance(raw_value, bool):
            return raw_value
        # String input (from environment variables)
        if isinstance(raw_value, str):
            lower = raw_value.strip().lower()
            if lower in ("true", "1", "yes", "on"):
                return True
            if lower in ("false", "0", "no", "off"):
                return False
        raise ConfigValidationError(
            f"Key '{key}': must be a boolean (true/false, 1/0, yes/no, on/off), "
            f"got: {raw_value!r}"
        )

    elif target_type == "enum":
        s = str(raw_value) if not isinstance(raw_value, str) else raw_value
        if s not in spec["allowed"]:
            raise ConfigValidationError(
                f"Key '{key}': must be one of {spec['allowed']} (got: {raw_value!r})"
            )
        return s

    # fallback — return as-is
    return raw_value
