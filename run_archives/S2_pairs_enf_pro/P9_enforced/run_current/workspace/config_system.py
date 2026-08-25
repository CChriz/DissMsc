"""
config_system.py — SPEC5: Worker Service Configuration System
Authoritative schema per spec/spec.md lines 1-158.
Implements the Celery worker configuration system with 11 keys,
4-layer priority cascade, type coercion, and validation.
"""

import json
import os


# ---- Exceptions ----
class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ---- Bool coercion helpers ----
_BOOL_TRUTHY = {"true", "1", "yes", "on"}
_BOOL_FALSY = {"false", "0", "no", "off"}


def _coerce_int(key, value):
    """Coerce value to int; raise ConfigValidationError on failure."""
    if isinstance(value, bool):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — expected integer"
        )
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — expected integer"
        )


def _coerce_bool(key, value):
    """Coerce value to bool using case-insensitive string matching."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _BOOL_TRUTHY:
            return True
        if lower in _BOOL_FALSY:
            return False
    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} — expected true/false/1/0/yes/no/on/off"
    )


def _coerce_enum(key, value, allowed):
    """Validate value is one of the allowed enum values."""
    if value not in allowed:
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — expected one of {allowed}"
        )
    return value


# ---- Schema ----
def get_schema():
    """Return the full 11-key Celery worker config schema."""
    return {
        "queue_url": {
            "type": "string",
            "default": "redis://localhost:6379/0",
            "env": "CELERY_QUEUE_URL",
            "validation": {"required": True, "non_empty": True},
        },
        "concurrency": {
            "type": "int",
            "default": 3,
            "env": "CELERY_CONCURRENCY",
            "validation": {"min": 1, "max": 32},
        },
        "max_retries": {
            "type": "int",
            "default": 8,
            "env": "CELERY_MAX_RETRIES",
            "validation": {"min": 0, "max": 20},
        },
        "retry_backoff_seconds": {
            "type": "int",
            "default": 1,
            "env": "CELERY_RETRY_BACKOFF",
            "validation": {"min": 1, "max": 300},
        },
        "job_timeout": {
            "type": "int",
            "default": 300,
            "env": "CELERY_JOB_TIMEOUT",
            "validation": {"min": 1, "max": 3600},
        },
        "log_level": {
            "type": "enum",
            "default": "INFO",
            "env": "CELERY_LOG_LEVEL",
            "validation": {"allowed": ["DEBUG", "INFO", "WARN"]},
        },
        "dead_letter_queue": {
            "type": "bool",
            "default": True,
            "env": "CELERY_DEAD_LETTER",
            "validation": {},
        },
        "heartbeat_interval": {
            "type": "int",
            "default": 60,
            "env": "CELERY_HEARTBEAT",
            "validation": {"min": 5, "max": 300},
        },
        "prefetch_count": {
            "type": "int",
            "default": 10,
            "env": "CELERY_PREFETCH",
            "validation": {"min": 1, "max": 100},
        },
        "ack_on_failure": {
            "type": "bool",
            "default": False,
            "env": "CELERY_ACK_ON_FAILURE",
            "validation": {},
        },
        "metrics_enabled": {
            "type": "bool",
            "default": True,
            "env": "CELERY_METRICS",
            "validation": {},
        },
    }


# ---- Public API ----
def validate_value(key, value):
    """
    Validate and coerce a single config value.
    Returns the coerced value; raises ConfigValidationError on failure.
    """
    schema = get_schema()
    if key not in schema:
        raise ConfigValidationError(f"Unknown config key: {key!r}")

    spec = schema[key]
    vtype = spec["type"]
    validation = spec.get("validation", {})

    # 1. Type coercion
    if vtype == "int":
        value = _coerce_int(key, value)
    elif vtype == "bool":
        value = _coerce_bool(key, value)
    elif vtype == "enum":
        value = _coerce_enum(key, value, validation["allowed"])
    # string: no coercion needed

    # 2. Validation rules (after coercion)
    if vtype == "int":
        if "min" in validation and value < validation["min"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value} — must be >= {validation['min']}"
            )
        if "max" in validation and value > validation["max"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value} — must be <= {validation['max']}"
            )
    elif vtype == "string":
        if validation.get("non_empty") and (not value or not str(value).strip()):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — must be non-empty"
            )

    return value


def load_config(config_file=None, env_vars=None, cli_args=None):
    """
    Load configuration with 4-layer priority cascade:
        CLI args > Env Vars > Config File > Built-in Defaults

    Args:
        config_file: Optional path to JSON config file.
        env_vars: Optional dict of environment variables (defaults to os.environ).
        cli_args: Optional dict of CLI arguments.

    Returns:
        dict with all 11 config keys, validated and coerced.
    """
    schema = get_schema()

    # Layer 4: Built-in defaults
    result = {key: spec["default"] for key, spec in schema.items()}

    # Layer 3: Config file
    if config_file is not None:
        with open(config_file) as f:
            file_data = json.load(f)
        for key in schema:
            if key in file_data:
                result[key] = file_data[key]

    # Layer 2: Environment variables
    source_env = env_vars if env_vars is not None else os.environ
    for key, spec in schema.items():
        env_name = spec["env"]
        if env_name in source_env:
            result[key] = source_env[env_name]

    # Layer 1: CLI args (highest priority)
    if cli_args is not None:
        for key in schema:
            if key in cli_args:
                result[key] = cli_args[key]

    # Validate & coerce all values
    for key in list(result.keys()):
        result[key] = validate_value(key, result[key])

    return result
