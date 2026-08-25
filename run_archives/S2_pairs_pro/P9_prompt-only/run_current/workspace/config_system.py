"""config_system.py — Worker Service Configuration System"""
import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# Full schema — 11 config keys with types, defaults, env vars, and validation rules
_SCHEMA: dict[str, dict] = {
    "queue_url": {
        "type": "string",
        "default": "redis://localhost:6379/0",
        "env_var": "CELERY_QUEUE_URL",
        "validation": {"kind": "non_empty"},
    },
    "concurrency": {
        "type": "int",
        "default": 3,
        "env_var": "CELERY_CONCURRENCY",
        "validation": {"kind": "range", "min": 1, "max": 32},
    },
    "max_retries": {
        "type": "int",
        "default": 8,
        "env_var": "CELERY_MAX_RETRIES",
        "validation": {"kind": "range", "min": 0, "max": 20},
    },
    "retry_backoff_seconds": {
        "type": "int",
        "default": 1,
        "env_var": "CELERY_RETRY_BACKOFF",
        "validation": {"kind": "range", "min": 1, "max": 300},
    },
    "job_timeout": {
        "type": "int",
        "default": 300,
        "env_var": "CELERY_JOB_TIMEOUT",
        "validation": {"kind": "range", "min": 1, "max": 3600},
    },
    "log_level": {
        "type": "enum",
        "default": "INFO",
        "env_var": "CELERY_LOG_LEVEL",
        "validation": {"kind": "allowed", "values": ["DEBUG", "INFO", "WARN"]},
    },
    "dead_letter_queue": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_DEAD_LETTER",
        "validation": {"kind": "bool"},
    },
    "heartbeat_interval": {
        "type": "int",
        "default": 60,
        "env_var": "CELERY_HEARTBEAT",
        "validation": {"kind": "range", "min": 5, "max": 300},
    },
    "prefetch_count": {
        "type": "int",
        "default": 10,
        "env_var": "CELERY_PREFETCH",
        "validation": {"kind": "range", "min": 1, "max": 100},
    },
    "ack_on_failure": {
        "type": "bool",
        "default": False,
        "env_var": "CELERY_ACK_ON_FAILURE",
        "validation": {"kind": "bool"},
    },
    "metrics_enabled": {
        "type": "bool",
        "default": True,
        "env_var": "CELERY_METRICS",
        "validation": {"kind": "bool"},
    },
}


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _coerce_int(key: str, value: Any) -> int:
    """Coerce a value to int with range validation."""
    if isinstance(value, bool):
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — expected an integer"
        )
    if isinstance(value, int):
        coerced = value
    elif isinstance(value, float):
        if value == int(value):
            coerced = int(value)
        else:
            raise ConfigValidationError(
                f"Invalid value for {key!r}: {value!r} — expected an integer"
            )
    elif isinstance(value, str):
        try:
            coerced = int(value)
        except ValueError:
            raise ConfigValidationError(
                f"Invalid value for {key!r}: {value!r} — expected an integer"
            )
    else:
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — expected an integer"
        )
    return coerced


def _coerce_bool(key: str, value: Any) -> bool:
    """Coerce a value to bool using explicit allowed strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value == 0:
            return False
        if value == 1:
            return True
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — expected true/false, 1/0, yes/no, on/off"
        )
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — expected true/false, 1/0, yes/no, on/off"
        )
    raise ConfigValidationError(
        f"Invalid value for {key!r}: {value!r} — expected true/false, 1/0, yes/no, on/off"
    )


def _coerce_enum(key: str, value: Any, allowed: list[str]) -> str:
    """Coerce and validate an enum value (case-sensitive)."""
    if not isinstance(value, str):
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — must be one of {allowed}"
        )
    if value not in allowed:
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — must be one of {allowed}"
        )
    return value


def _coerce_string(key: str, value: Any) -> str:
    """Coerce to string and validate non-empty."""
    if not isinstance(value, str):
        coerced = str(value)
    else:
        coerced = value
    if len(coerced.strip()) == 0:
        raise ConfigValidationError(
            f"Invalid value for {key!r}: {value!r} — must be a non-empty string"
        )
    return coerced


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value for the given config key."""
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: {key!r}")

    spec = _SCHEMA[key]
    kind = spec["type"]
    validation = spec.get("validation", {})

    if kind == "int":
        coerced = _coerce_int(key, value)
        if validation.get("kind") == "range":
            vmin = validation["min"]
            vmax = validation["max"]
            if not (vmin <= coerced <= vmax):
                raise ConfigValidationError(
                    f"Invalid value for {key!r}: {value!r} — must be in range [{vmin}, {vmax}]"
                )
        return coerced

    elif kind == "bool":
        return _coerce_bool(key, value)

    elif kind == "enum":
        allowed = validation.get("values", [])
        return _coerce_enum(key, value, allowed)

    elif kind == "string":
        return _coerce_string(key, value)

    else:
        raise ConfigValidationError(f"Unknown type {kind!r} for key {key!r}")


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): CLI args > env vars > config file > defaults
    """
    # Step 1: Start with defaults
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2: Merge config file (lowest priority, above defaults only)
    if config_file is not None:
        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Config file not found: {config_file}")
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        for key, raw_value in file_data.items():
            if key in _SCHEMA and raw_value is not None:
                result[key] = raw_value

    # Step 3: Merge environment variables (second priority)
    env_source = env_vars if env_vars is not None else os.environ
    for key, spec in _SCHEMA.items():
        env_name = spec["env_var"]
        if env_name in env_source:
            result[key] = env_source[env_name]

    # Step 4: Merge CLI args (highest priority)
    if cli_args is not None:
        for key, raw_value in cli_args.items():
            if key in _SCHEMA and raw_value is not None:
                result[key] = raw_value

    # Step 5: Type coercion and validation
    for key in result:
        result[key] = validate_value(key, result[key])

    # Step 6: Return
    return result


def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    return dict(_SCHEMA)
