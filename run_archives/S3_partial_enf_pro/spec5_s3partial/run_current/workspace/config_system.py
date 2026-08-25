"""
Configuration system for the Web Service application.
Implements multi-source config loading with priority cascade,
type coercion, and validation.

Priority (highest first): cli_args > env_vars > config_file > defaults
"""

import copy
import json
import os
from typing import Any


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ---------------------------------------------------------------------------
# Full schema — 10 configuration keys per spec.md
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env": "WEB_HOST",
        "validation": "non_empty_string",
        "description": "Hostname or IP address to bind",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env": "WEB_PORT",
        "validation": "range",
        "range": [2048, 49151],
        "description": "TCP port to listen on",
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env": "WEB_LOG_LEVEL",
        "allowed": ["INFO", "WARN", "ERROR"],
        "description": "Logging verbosity",
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env": "WEB_REQUEST_TIMEOUT",
        "validation": "range",
        "range": [1, 3600],
        "description": "Request timeout in seconds",
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env": "WEB_MAX_CONNECTIONS",
        "validation": "range",
        "range": [1, 1000],
        "description": "Maximum concurrent connections",
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env": "WEB_DEBUG",
        "description": "Enable debug mode",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env": "WEB_STATIC_DIR",
        "validation": "non_empty_string",
        "description": "Path to static files directory",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env": "WEB_CORS_ORIGINS",
        "description": "Allowed CORS origins, comma-separated",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": "range",
        "range": [1, 300],
        "description": "Keep-alive timeout seconds",
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env": "WEB_SSL_ENABLED",
        "description": "Enable SSL/TLS",
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_value(key: str, value: Any, spec: dict) -> Any:
    """Coerce a raw value to the target type defined in the schema."""
    typ = spec["type"]

    if typ == "string":
        return str(value)

    elif typ == "int":
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid integer value for '{key}': {value!r}"
            )

    elif typ == "float":
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid float value for '{key}': {value!r}"
            )

    elif typ == "bool":
        # bool is a subclass of int — check it FIRST
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
            raise ConfigValidationError(
                f"Invalid bool value for '{key}': {value!r}"
            )
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "1", "yes", "on"):
                return True
            if v in ("false", "0", "no", "off"):
                return False
            raise ConfigValidationError(
                f"Invalid bool value for '{key}': {value!r}"
            )
        raise ConfigValidationError(
            f"Invalid bool value for '{key}': {value!r}"
        )

    elif typ == "enum":
        s = str(value)
        if s not in spec.get("allowed", []):
            raise ConfigValidationError(
                f"Invalid enum value for '{key}': {value!r}. "
                f"Allowed: {spec['allowed']}"
            )
        return s

    # fallback — shouldn't happen for valid schema
    return value


def _validate_value(key: str, value: Any, spec: dict) -> Any:
    """Validate a coerced value against schema constraints (range, enum, etc.)."""
    typ = spec["type"]

    if typ == "string":
        validation = spec.get("validation")
        if validation == "non_empty_string":
            if not isinstance(value, str) or value == "":
                raise ConfigValidationError(
                    f"Invalid value for '{key}': must be a non-empty string, "
                    f"got {value!r}"
                )
        return value

    elif typ == "int":
        validation = spec.get("validation")
        if validation == "range":
            lo, hi = spec["range"]
            if not (lo <= value <= hi):
                raise ConfigValidationError(
                    f"Invalid value for '{key}': {value} not in range [{lo}, {hi}]"
                )
        return value

    elif typ == "enum":
        # Already validated during coercion; just pass through
        return value

    elif typ == "bool":
        return value

    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_value(key: str, value: Any) -> Any:
    """
    Validate and coerce a single value for the given config key.

    Raises ConfigValidationError if the key is unknown or the value is invalid.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: '{key}'")
    spec = _SCHEMA[key]
    coerced = _coerce_value(key, value, spec)
    return _validate_value(key, coerced, spec)


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """
    Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    Parameters
    ----------
    config_file : str or None
        Path to a JSON config file.
    env_vars : dict or None
        Environment variables dict (defaults to os.environ).
    cli_args : dict or None
        CLI argument overrides.

    Returns
    -------
    dict
        Fully-resolved, coerced, and validated config dict with all 10 keys.
    """
    # --- 4th layer: defaults ---
    result: dict[str, Any] = {key: spec["default"] for key, spec in _SCHEMA.items()}

    # --- 3rd layer: JSON config file ---
    if config_file is not None:
        try:
            with open(config_file, "r") as f:
                file_data = json.load(f)
        except FileNotFoundError:
            raise  # re-raise FileNotFoundError as-is
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"Invalid JSON in config file: {e}")

        for key, spec in _SCHEMA.items():
            if key in file_data and file_data[key] is not None:
                result[key] = file_data[key]

    # --- 2nd layer: environment variables ---
    if env_vars is None:
        env_vars = os.environ

    env_map = {spec["env"]: key for key, spec in _SCHEMA.items()}
    for env_name, key in env_map.items():
        if env_name in env_vars:
            val = env_vars[env_name]
            if val is not None and val != "":
                result[key] = val

    # --- 1st layer (highest priority): CLI args ---
    if cli_args:
        for key in _SCHEMA:
            if key in cli_args and cli_args[key] is not None:
                result[key] = cli_args[key]

    # --- Final pass: coerce + validate every key ---
    final: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        raw_value = result[key]
        coerced = _coerce_value(key, raw_value, spec)
        validated = _validate_value(key, coerced, spec)
        final[key] = validated

    return final


def get_schema() -> dict:
    """Return a deep copy of the config schema."""
    return copy.deepcopy(_SCHEMA)
