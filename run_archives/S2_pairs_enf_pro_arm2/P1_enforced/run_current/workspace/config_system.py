"""
Configuration system for the Worker Service.

Implements:
    - ConfigValidationError : exception hierarchy (subclass of ValueError)
    - get_schema()          : full configuration schema (11 keys)
    - validate_value()      : single-value validation + type coercion
    - load_config()         : multi-source loading with priority cascade

Priority cascade (highest first):
    cli_args > env_vars > config_file > defaults

The runtime schema in ``get_schema()`` is the single source of truth.
"""

import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


_TRUE_STRINGS = {"true", "1", "yes", "on"}
_FALSE_STRINGS = {"false", "0", "no", "off"}


def get_schema() -> dict:
    """Return the full configuration schema keyed by config key name."""
    return {
        "queue_url": {
            "type": "string",
            "default": "redis://localhost:6379/0",
            "env": "CELERY_QUEUE_URL",
            "non_empty": True,
        },
        "concurrency": {
            "type": "int",
            "default": 3,
            "env": "CELERY_CONCURRENCY",
            "min": 1,
            "max": 32,
        },
        "max_retries": {
            "type": "int",
            "default": 8,
            "env": "CELERY_MAX_RETRIES",
            "min": 0,
            "max": 20,
        },
        "retry_backoff_seconds": {
            "type": "int",
            "default": 1,
            "env": "CELERY_RETRY_BACKOFF",
            "min": 1,
            "max": 300,
        },
        "job_timeout": {
            "type": "int",
            "default": 300,
            "env": "CELERY_JOB_TIMEOUT",
            "min": 1,
            "max": 3600,
        },
        "log_level": {
            "type": "enum",
            "default": "INFO",
            "env": "CELERY_LOG_LEVEL",
            "allowed": ["DEBUG", "INFO", "WARN"],
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
            "min": 5,
            "max": 300,
        },
        "prefetch_count": {
            "type": "int",
            "default": 10,
            "env": "CELERY_PREFETCH",
            "min": 1,
            "max": 100,
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


def _coerce_int(key: str, value: Any, spec: dict) -> int:
    """Coerce ``value`` to int per the strict int coercion matrix."""
    if isinstance(value, bool):
        # bool is a subclass of int; reject it to avoid 1/0 ambiguity.
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid integer"
        )

    if isinstance(value, int):
        v = value
    elif isinstance(value, float):
        if value.is_integer():
            v = int(value)
        else:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} is not a valid integer"
            )
    elif isinstance(value, str):
        s = value.strip()
        if s == "":
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} is not a valid integer"
            )
        try:
            v = int(s)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} is not a valid integer"
            )
    else:
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid integer"
        )

    lo = spec.get("min")
    hi = spec.get("max")
    if lo is not None and hi is not None and not (lo <= v <= hi):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} must be in range [{lo}, {hi}]"
        )

    return v


def _coerce_float(key: str, value: Any) -> float:
    """Coerce ``value`` to float."""
    if isinstance(value, bool):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid float"
        )

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        s = value.strip()
        try:
            return float(s)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} is not a valid float"
            )

    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} is not a valid float"
    )


def _coerce_bool(key: str, value: Any) -> bool:
    """Coerce ``value`` to bool per the bool coercion matrix."""
    if isinstance(value, bool):
        return value

    if isinstance(value, int) and value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        s = value.strip().lower()
        if s in _TRUE_STRINGS:
            return True
        if s in _FALSE_STRINGS:
            return False
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid boolean"
        )

    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} is not a valid boolean"
    )


def _coerce_enum(key: str, value: Any, spec: dict) -> str:
    """Coerce ``value`` to one of the allowed enum values (case-sensitive)."""
    if not isinstance(value, str):
        value = str(value)

    allowed = spec["allowed"]
    if value not in allowed:
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} must be one of {allowed}"
        )

    return value


def _coerce_string(key: str, value: Any, spec: dict) -> str:
    """Coerce ``value`` to str (as-is semantics for existing strings)."""
    if not isinstance(value, str):
        value = str(value)

    if spec.get("non_empty") and value == "":
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} must not be empty"
        )

    return value


def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value for the given config key.

    Raises ``ConfigValidationError`` on any failure. Unknown keys are rejected.
    """
    schema = get_schema()
    spec = schema.get(key)
    if spec is None:
        raise ConfigValidationError(f"Unknown config key: '{key}'")

    vtype = spec["type"]
    if vtype == "int":
        return _coerce_int(key, value, spec)
    if vtype == "float":
        return _coerce_float(key, value)
    if vtype == "bool":
        return _coerce_bool(key, value)
    if vtype == "enum":
        return _coerce_enum(key, value, spec)
    if vtype == "string":
        return _coerce_string(key, value, spec)

    # Unknown schema type is a programming error, not a user config error.
    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} has unknown schema type {vtype!r}"
    )


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    A source value of ``None`` is treated as "not provided" and skipped.
    A source value of ``""`` (empty string) is treated as "provided" and
    participates in the priority override normally.
    """
    if env_vars is None:
        env_vars = os.environ
    if cli_args is None:
        cli_args = {}

    schema = get_schema()

    # 1) Lowest priority: defaults.
    merged = {k: spec["default"] for k, spec in schema.items()}

    # 2) config_file (priority 3).
    if config_file is not None:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in schema and v is not None:
                merged[k] = v

    # 3) env_vars (priority 2) — mapped by env name, not config key.
    for k, spec in schema.items():
        env_name = spec["env"]
        if env_name in env_vars and env_vars[env_name] is not None:
            merged[k] = env_vars[env_name]

    # 4) cli_args (priority 1, highest) — mapped by config key.
    for k, v in cli_args.items():
        if k in schema and v is not None:
            merged[k] = v

    # 5) Full validation + coercion.
    return {k: validate_value(k, merged[k]) for k in schema}
