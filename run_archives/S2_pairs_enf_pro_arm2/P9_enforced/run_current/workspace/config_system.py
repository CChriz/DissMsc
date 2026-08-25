"""Worker Service configuration system (SPEC5).

Implements a schema-driven configuration loader with an explicit priority
cascade (CLI > environment variables > config file > built-in defaults) and
strict type coercion / validation for every configuration key.

This module is self-contained: the module-level SCHEMA constant is the single
source of truth for keys, types, defaults, environment variable names and
validation constraints. ``get_schema()``, ``validate_value()`` and
``load_config()`` all read from this same SCHEMA and never duplicate it.
"""

from __future__ import annotations

import copy
import json
import os


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""

    pass


# ---------------------------------------------------------------------------
# Configuration schema — single source of truth
# ---------------------------------------------------------------------------
SCHEMA = {
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


def get_schema() -> dict:
    """Return the config schema as a dict (key -> spec dict)."""
    return copy.deepcopy(SCHEMA)


def _coerce(key: str, value, spec: dict):
    """Coerce ``value`` to the schema type for ``key``.

    Raises ``ConfigValidationError`` on any failure. Every error message
    includes both the key name and the offending value.
    """
    t = spec["type"]

    if t == "int":
        # bool is a subclass of int; reject it explicitly to avoid True -> 1.
        if isinstance(value, bool):
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} (must be an integer)"
            )
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                raise ConfigValidationError(
                    f"invalid value for '{key}': {value!r} (must be an integer)"
                )
        # Reject floats, lists, etc. — never silently truncate via int().
        raise ConfigValidationError(
            f"invalid value for '{key}': {value!r} (must be an integer)"
        )

    if t == "float":
        if isinstance(value, bool):
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} (must be a float)"
            )
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                raise ConfigValidationError(
                    f"invalid value for '{key}': {value!r} (must be a float)"
                )
        raise ConfigValidationError(
            f"invalid value for '{key}': {value!r} (must be a float)"
        )

    if t == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            v = value.strip().lower()
            if v in {"true", "1", "yes", "on"}:
                return True
            if v in {"false", "0", "no", "off"}:
                return False
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} (must be a boolean)"
            )
        # Lenient compatibility: integer 0 / 1 only.
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise ConfigValidationError(
            f"invalid value for '{key}': {value!r} (must be a boolean)"
        )

    if t == "enum":
        if not isinstance(value, str):
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} "
                f"(must be one of {spec['allowed']!r})"
            )
        # Exact, case-sensitive match — no strip, no lower.
        if value not in spec["allowed"]:
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} "
                f"(must be one of {spec['allowed']!r})"
            )
        return value

    if t == "string":
        if not isinstance(value, str):
            raise ConfigValidationError(
                f"invalid value for '{key}': {value!r} (must be a string)"
            )
        return value

    # Unreachable with the current schema, kept as a defensive guard.
    raise ConfigValidationError(f"invalid value for '{key}': {value!r} (unknown type {t!r})")


def validate_value(key: str, value) -> object:
    """Validate and coerce a single value against the schema for ``key``."""
    spec = SCHEMA.get(key)
    if spec is None:
        raise ConfigValidationError(f"unknown config key: {key!r}")

    coerced = _coerce(key, value, spec)

    # Post-coercion constraints.
    if spec["type"] == "string" and spec.get("non_empty") and coerced == "":
        raise ConfigValidationError(
            f"invalid value for '{key}': '' (must be a non-empty string)"
        )
    if spec["type"] == "int":
        lo, hi = spec.get("min"), spec.get("max")
        if (lo is not None and coerced < lo) or (hi is not None and coerced > hi):
            raise ConfigValidationError(
                f"invalid value for '{key}': {coerced!r} "
                f"(must be in range [{lo}, {hi}])"
            )

    return coerced


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load configuration with priority CLI > env vars > config file > defaults.

    ``env_vars`` uses environment variable names as keys (e.g.
    ``"CELERY_CONCURRENCY"``); ``cli_args`` and the JSON config file use the
    configuration key names (e.g. ``"concurrency"``).
    """
    if env_vars is None:
        env_vars = os.environ
    cli_args = cli_args or {}

    # 1) Built-in defaults form the base layer.
    merged = {k: spec["default"] for k, spec in SCHEMA.items()}

    # 2) Config file overrides defaults.
    if config_file is not None:
        with open(config_file, "r", encoding="utf-8") as f:
            file_data = json.load(f)
        if not isinstance(file_data, dict):
            raise ConfigValidationError(
                f"config file must be a JSON object, got {type(file_data).__name__}"
            )
        for k in SCHEMA:
            if k in file_data and file_data[k] is not None:
                merged[k] = file_data[k]

    # 3) Environment variables override the config file.
    for k, spec in SCHEMA.items():
        env_name = spec["env"]
        if env_name in env_vars and env_vars[env_name] is not None:
            merged[k] = env_vars[env_name]

    # 4) CLI args override environment variables (highest priority).
    for k in SCHEMA:
        if k in cli_args and cli_args[k] is not None:
            merged[k] = cli_args[k]

    # 5) Coerce and validate every key.
    result = {}
    for k in SCHEMA:
        result[k] = validate_value(k, merged[k])
    return result
