"""
Configuration system for the web service application.

Implements load_config, get_schema, and validate_value with full
priority cascade: CLI args > env vars > config file > defaults.
"""

import copy
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
# Schema
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env": "WEB_HOST",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env": "WEB_PORT",
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env": "WEB_LOG_LEVEL",
        "allowed": {"INFO", "WARN", "ERROR"},
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env": "WEB_REQUEST_TIMEOUT",
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env": "WEB_MAX_CONNECTIONS",
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env": "WEB_DEBUG",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env": "WEB_STATIC_DIR",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env": "WEB_CORS_ORIGINS",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env": "WEB_KEEP_ALIVE_TIMEOUT",
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env": "WEB_SSL_ENABLED",
    },
}

# Reverse index: env var name -> config key
_ENV_MAP: dict[str, str] = {
    spec["env"]: key for key, spec in _SCHEMA.items()
}

# Keys whose string values must be non-empty
_NON_EMPTY_STRING_KEYS = {"host", "static_dir"}


# ---------------------------------------------------------------------------
# Internal coercion helpers
# ---------------------------------------------------------------------------

def _coerce_int(key: str, value: Any) -> int:
    """Coerce *value* to int for *key*; raise ConfigValidationError on failure."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid int for '{key}': {value!r}"
            )
    raise ConfigValidationError(
        f"Invalid int for '{key}': {value!r}"
    )


def _coerce_float(key: str, value: Any) -> float:
    """Coerce *value* to float for *key*; raise ConfigValidationError on failure."""
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid float for '{key}': {value!r}"
            )
    raise ConfigValidationError(
        f"Invalid float for '{key}': {value!r}"
    )


def _coerce_bool(key: str, value: Any) -> bool:
    """Coerce *value* to bool for *key*; raise ConfigValidationError on failure."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.lower().strip()
        if lower in ("true", "1", "yes", "on"):
            return True
        if lower in ("false", "0", "no", "off"):
            return False
        if lower == "":
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} — empty string cannot be parsed as bool"
            )
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — cannot parse as bool"
        )
    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} — cannot parse as bool"
    )


def _coerce_enum(key: str, value: Any, allowed: set) -> str:
    """Validate *value* is in *allowed* set; raise ConfigValidationError otherwise."""
    if isinstance(value, str):
        if value in allowed:
            return value
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — must be one of {sorted(allowed)}"
        )
    raise ConfigValidationError(
        f"Invalid value for '{key}': {value!r} — must be one of {sorted(allowed)}"
    )


def _coerce_string(key: str, value: Any) -> str:
    """Coerce *value* to string; enforce non-empty constraint where applicable."""
    if not isinstance(value, str):
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — expected a string"
        )
    if key in _NON_EMPTY_STRING_KEYS and value == "":
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} — must be a non-empty string"
        )
    return value


def _coerce_value(key: str, raw_value: Any, spec: dict) -> Any:
    """Dispatch coercion based on spec type."""
    stype = spec["type"]

    if stype == "string":
        return _coerce_string(key, raw_value)
    elif stype == "int":
        return _coerce_int(key, raw_value)
    elif stype == "float":
        return _coerce_float(key, raw_value)
    elif stype == "bool":
        return _coerce_bool(key, raw_value)
    elif stype == "enum":
        allowed = spec.get("allowed", set())
        return _coerce_enum(key, raw_value, allowed)
    else:
        raise ConfigValidationError(
            f"Unknown type '{stype}' for key '{key}'"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema() -> dict:
    """Return a deep copy of the configuration schema.

    Returns:
        dict: A dictionary mapping config keys to their specification dicts.
              Each spec contains at least ``type``, ``default``, and ``env``.
    """
    return copy.deepcopy(_SCHEMA)


def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single configuration value.

    Args:
        key:   The configuration key (must exist in the schema).
        value: The raw value to validate and coerce.

    Returns:
        The coerced value.

    Raises:
        ConfigValidationError: If *key* is unknown or *value* is invalid.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: {key!r}")
    spec = _SCHEMA[key]
    return _coerce_value(key, value, spec)


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and return a fully-resolved configuration dictionary.

    Priority (highest first):
        1. CLI args (*cli_args*)
        2. Environment variables (*env_vars* or ``os.environ``)
        3. JSON config file (*config_file*)
        4. Schema defaults

    Values from lower-priority sources are overwritten by higher-priority
    sources.  Every value is coerced and validated according to the schema.

    Args:
        config_file: Optional path to a JSON configuration file.
        env_vars:    Optional dict of environment variables (defaults to
                     ``os.environ``).
        cli_args:    Optional dict of CLI-supplied overrides.

    Returns:
        dict: Fully-resolved configuration.

    Raises:
        FileNotFoundError: If *config_file* is provided but does not exist.
        ConfigValidationError: If any value fails validation.
    """
    # Step 1: Load defaults
    result: dict[str, Any] = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2: Overlay config file (if provided)
    if config_file is not None:
        if not os.path.isfile(config_file):
            raise FileNotFoundError(
                f"Config file not found: {config_file!r}"
            )
        with open(config_file, "r", encoding="utf-8") as fh:
            file_data = json.load(fh)
        for key, raw_value in file_data.items():
            if key in _SCHEMA:
                result[key] = _coerce_value(key, raw_value, _SCHEMA[key])

    # Step 3: Overlay environment variables
    env_source = env_vars if env_vars is not None else os.environ
    for env_name, config_key in _ENV_MAP.items():
        if env_name in env_source:
            result[config_key] = _coerce_value(
                config_key, env_source[env_name], _SCHEMA[config_key]
            )

    # Step 4: Overlay CLI args (highest priority)
    if cli_args is not None:
        for key, raw_value in cli_args.items():
            if key in _SCHEMA:
                result[key] = _coerce_value(key, raw_value, _SCHEMA[key])

    return result
