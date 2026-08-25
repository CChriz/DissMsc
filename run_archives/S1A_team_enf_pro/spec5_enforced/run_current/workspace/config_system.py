"""
Configuration system for the Web Service application.

Implements config loading with priority cascade:
    CLI args > Env vars > Config file > Defaults

Provides type coercion, validation, and a schema for all 10 config keys.
"""

import json
import os
from typing import Any


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ---------------------------------------------------------------------------
# Full Schema — 10 config keys
# ---------------------------------------------------------------------------

SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "validation": {"kind": "non_empty_string"},
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "validation": {"kind": "range", "min": 2048, "max": 49151},
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "allowed": ["INFO", "WARN", "ERROR"],
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "validation": {"kind": "range", "min": 1, "max": 3600},
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validation": {"kind": "range", "min": 1, "max": 1000},
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "validation": {"kind": "non_empty_string"},
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": {"kind": "range", "min": 1, "max": 300},
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
    },
}


# ---------------------------------------------------------------------------
# Environment variable → config key mapping
# ---------------------------------------------------------------------------

ENV_KEY_MAP: dict[str, str] = {
    "WEB_HOST": "host",
    "WEB_PORT": "port",
    "WEB_LOG_LEVEL": "log_level",
    "WEB_REQUEST_TIMEOUT": "request_timeout",
    "WEB_MAX_CONNECTIONS": "max_connections",
    "WEB_DEBUG": "debug_mode",
    "WEB_STATIC_DIR": "static_dir",
    "WEB_CORS_ORIGINS": "cors_origins",
    "WEB_KEEP_ALIVE_TIMEOUT": "keep_alive_timeout",
    "WEB_SSL_ENABLED": "ssl_enabled",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema() -> dict:
    """Return the full config schema."""
    return SCHEMA


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _coerce_bool(key: str, value) -> bool:
    """Coerce a value to bool. Accepts bool, int 0/1, and common string forms."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if int(value) in (0, 1):
            return bool(int(value))
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid boolean"
        )
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("false", "0", "no", "off"):
        return False
    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} is not a valid boolean"
    )


def _coerce_int(key: str, value) -> int:
    """Coerce a value to int. Rejects float values."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid integer"
        )
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid integer"
        )


def _coerce_float(key: str, value) -> float:
    """Coerce a value to float. Reserved for future use."""
    try:
        return float(value)
    except (ValueError, TypeError):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} is not a valid float"
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_value(key: str, value) -> object:
    """Validate and coerce a single value for the given config key.

    Returns the coerced value on success.  Raises ConfigValidationError
    when the value cannot be coerced or does not satisfy the schema rules.
    """
    spec = SCHEMA[key]
    vtype = spec["type"]

    if vtype == "bool":
        coerced = _coerce_bool(key, value)
    elif vtype == "int":
        coerced = _coerce_int(key, value)
        v = spec.get("validation")
        if v and v.get("kind") == "range":
            if coerced < v["min"] or coerced > v["max"]:
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {coerced} not in range "
                    f"[{v['min']}, {v['max']}]"
                )
    elif vtype == "float":
        coerced = _coerce_float(key, value)
    elif vtype == "enum":
        coerced = str(value)
        if coerced not in spec["allowed"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} not in allowed values: "
                f"{spec['allowed']}"
            )
    elif vtype == "string":
        coerced = str(value)
        v = spec.get("validation")
        if v and v.get("kind") == "non_empty_string":
            if not coerced or len(coerced) == 0:
                raise ConfigValidationError(
                    f"Invalid value for '{key}': value must be a non-empty string"
                )
    else:
        coerced = value

    return coerced


# ---------------------------------------------------------------------------
# Config loading with priority cascade
# ---------------------------------------------------------------------------

def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    Parameters
    ----------
    config_file : str | None
        Path to a JSON config file.  FileNotFoundError is raised if the path
        does not exist.
    env_vars : dict | None
        Environment variable dict.  Defaults to ``os.environ`` when None.
    cli_args : dict | None
        CLI-supplied overrides.  Unknown keys are ignored.

    Returns
    -------
    dict
        Fully resolved, validated configuration dict.
    """
    # Step 1 — start from defaults
    result: dict[str, Any] = {
        key: spec["default"] for key, spec in SCHEMA.items()
    }

    # Step 2 — merge config file (priority 3)
    if config_file is not None:
        with open(config_file, "r") as f:
            file_data = json.load(f)
        for key, value in file_data.items():
            if key in SCHEMA:
                result[key] = value

    # Step 3 — merge environment variables (priority 2)
    if env_vars is None:
        env_vars = os.environ

    for env_name, config_key in ENV_KEY_MAP.items():
        if env_name in env_vars:
            result[config_key] = env_vars[env_name]

    # Step 4 — merge CLI args (priority 1, highest)
    if cli_args:
        for key, value in cli_args.items():
            if key in SCHEMA:
                result[key] = value

    # Step 5 — validate every key
    for key in SCHEMA:
        result[key] = validate_value(key, result[key])

    return result
