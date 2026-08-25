"""
Configuration system for the web service application.

Implements layered configuration loading with priority cascade:
    CLI args > environment variables > config file > defaults

Provides type coercion, validation, and schema introspection.
"""

import copy
import json
import os
from typing import Any


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ConfigValidationError(ValueError):
    """Raised when a configuration value fails validation or type coercion.

    Message format: "Key '<key>': <reason>"
    """

    pass


# ---------------------------------------------------------------------------
# Schema — single source of truth
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, dict] = {
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
        "validation": {"kind": "int_range", "min": 2048, "max": 49151},
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "validation": {"kind": "enum", "allowed": ["INFO", "WARN", "ERROR"]},
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "validation": {"kind": "int_range", "min": 1, "max": 3600},
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validation": {"kind": "int_range", "min": 1, "max": 1000},
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
        "validation": {"kind": "bool"},
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
        "validation": {"kind": "string_any"},
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": {"kind": "int_range", "min": 1, "max": 300},
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
        "validation": {"kind": "bool"},
    },
}

# Reverse mapping: env_var → config key name
_ENV_TO_KEY: dict[str, str] = {
    spec["env_var"]: key for key, spec in _SCHEMA.items()
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_schema() -> dict:
    """Return a deep copy of the full configuration schema."""
    return copy.deepcopy(_SCHEMA)


def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value for the given configuration key.

    If the key is not in the schema the value is returned unchanged (unknown
    keys from external sources are silently tolerated by higher layers).
    """
    spec = _SCHEMA.get(key)
    if spec is None:
        # Unknown key — pass through unchanged (callers handle filtering)
        return value
    return _coerce_and_validate(key, value, spec)


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration with priority cascade.

    Priority (highest first):
        cli_args > env_vars > config_file > schema defaults

    Parameters
    ----------
    config_file : str | None
        Path to a JSON config file.  ``None`` skips the file layer.
    env_vars : dict | None
        Dictionary of environment variables.  ``None`` reads from
        ``os.environ``.
    cli_args : dict | None
        CLI-supplied overrides (highest priority).

    Returns
    -------
    dict
        Fully validated configuration dictionary.

    Raises
    ------
    FileNotFoundError
        When *config_file* is not ``None`` and the file does not exist.
    ConfigValidationError
        When any value fails type coercion or validation.
    """
    # ---- step 1: start with schema defaults ----
    result: dict[str, Any] = {
        key: spec["default"] for key, spec in _SCHEMA.items()
    }

    # ---- step 2: merge config file (lowest dynamic priority) ----
    if config_file is not None:
        if not os.path.isfile(config_file):
            raise FileNotFoundError(
                f"Configuration file not found: {config_file}"
            )
        with open(config_file, "r", encoding="utf-8") as fh:
            file_data = json.load(fh)
        for key, value in file_data.items():
            if key in _SCHEMA and value is not None:
                result[key] = value

    # ---- step 3: merge environment variables ----
    env_source = env_vars if env_vars is not None else os.environ
    for env_var_name, key in _ENV_TO_KEY.items():
        if env_var_name in env_source:
            val = env_source[env_var_name]
            if val is not None:
                result[key] = val

    # ---- step 4: merge CLI args (highest priority) ----
    if cli_args is not None:
        for key, value in cli_args.items():
            if key in _SCHEMA and value is not None:
                result[key] = value

    # ---- step 5: validate every key ----
    validated: dict[str, Any] = {}
    for key in result:
        validated[key] = validate_value(key, result[key])

    return validated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_and_validate(key: str, value: Any, spec: dict) -> Any:
    """Coerce *value* to *spec["type"]* and run *spec["validation"]*.

    Raises ConfigValidationError with an actionable message on failure.
    """
    vtype = spec["type"]
    validation = spec["validation"]

    # --------------- coercion ---------------
    coerced: Any

    if vtype == "string":
        coerced = str(value)

    elif vtype == "int":
        # Guard: bool is a subclass of int in Python
        if isinstance(value, bool):
            raise ConfigValidationError(
                f"Key '{key}': cannot coerce '{value}' to int"
            )
        if isinstance(value, int):
            coerced = value
        elif isinstance(value, float):
            # Reject non-integer floats to avoid silent precision loss
            if value != int(value):
                raise ConfigValidationError(
                    f"Key '{key}': cannot coerce '{value}' to int"
                )
            coerced = int(value)
        elif isinstance(value, str):
            try:
                coerced = int(value)
            except ValueError:
                raise ConfigValidationError(
                    f"Key '{key}': cannot coerce '{value}' to int"
                )
        else:
            raise ConfigValidationError(
                f"Key '{key}': cannot coerce '{value}' to int"
            )

    elif vtype == "float":
        if isinstance(value, bool):
            raise ConfigValidationError(
                f"Key '{key}': cannot coerce '{value}' to float"
            )
        if isinstance(value, (int, float)):
            coerced = float(value)
        elif isinstance(value, str):
            try:
                coerced = float(value)
            except ValueError:
                raise ConfigValidationError(
                    f"Key '{key}': cannot coerce '{value}' to float"
                )
        else:
            raise ConfigValidationError(
                f"Key '{key}': cannot coerce '{value}' to float"
            )

    elif vtype == "bool":
        if isinstance(value, bool):
            coerced = value
        elif isinstance(value, int):
            if value in (0, 1):
                coerced = bool(value)
            else:
                raise ConfigValidationError(
                    f"Key '{key}': cannot coerce '{value}' to bool"
                )
        elif isinstance(value, str):
            vlow = value.lower()
            if vlow in ("true", "1", "yes", "on"):
                coerced = True
            elif vlow in ("false", "0", "no", "off"):
                coerced = False
            else:
                raise ConfigValidationError(
                    f"Key '{key}': cannot coerce '{value}' to bool"
                )
        else:
            raise ConfigValidationError(
                f"Key '{key}': cannot coerce '{value}' to bool"
            )

    elif vtype == "enum":
        # Coerce to string first, then validate against allowed values
        coerced = str(value)

    else:
        # Defensive: unknown type — pass through
        coerced = value

    # --------------- validation ---------------
    kind = validation["kind"]

    if kind == "non_empty_string":
        if not isinstance(coerced, str) or coerced == "":
            raise ConfigValidationError(
                f"Key '{key}': value must be a non-empty string"
            )

    elif kind == "string_any":
        # Ensure the final value is a string
        coerced = str(coerced)

    elif kind == "int_range":
        if not (validation["min"] <= coerced <= validation["max"]):
            raise ConfigValidationError(
                f"Key '{key}': value {coerced} not in range "
                f"[{validation['min']}, {validation['max']}]"
            )

    elif kind == "enum":
        if coerced not in validation["allowed"]:
            allowed_repr = str(validation["allowed"])
            raise ConfigValidationError(
                f"Key '{key}': value '{coerced}' not in {allowed_repr}"
            )

    elif kind == "bool":
        # Already coerced — nothing extra to validate
        pass

    return coerced
