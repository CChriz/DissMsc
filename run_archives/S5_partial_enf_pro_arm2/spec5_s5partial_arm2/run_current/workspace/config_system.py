"""
Configuration system for the web service application.

Implements layered configuration loading with priority cascade:
CLI args > environment variables > config file > defaults

All 10 configuration keys are defined in _SCHEMA with their types,
defaults, environment variable mappings, and validation rules.
"""

import json
import os
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when a config value fails validation or type coercion."""
    pass


_SCHEMA: dict[str, dict] = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "validation": "non_empty",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "validation": "range",
        "min": 2048,
        "max": 49151,
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
        "validation": "range",
        "min": 1,
        "max": 3600,
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validation": "range",
        "min": 1,
        "max": 1000,
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
        "validation": None,
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "validation": "non_empty",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
        "validation": None,
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validation": "range",
        "min": 1,
        "max": 300,
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
        "validation": None,
    },
}

# Truthy / falsy string sets for bool coercion (case-insensitive matching)
_TRUTHY_STRINGS = frozenset({"true", "1", "yes", "on"})
_FALSY_STRINGS = frozenset({"false", "0", "no", "off"})


def _coerce_value(key: str, raw: Any, schema_entry: dict) -> Any:
    """Coerce a raw value to the expected type per the schema entry.

    Args:
        key: The config key name (used in error messages).
        raw: The raw input value to coerce.
        schema_entry: The schema dict for this key (must have 'type').

    Returns:
        The coerced value.

    Raises:
        ConfigValidationError: If coercion fails.
    """
    target_type = schema_entry["type"]

    # --- string: return as-is ---
    if target_type == "string":
        if not isinstance(raw, str):
            raw = str(raw)
        return raw

    # --- int ---
    if target_type == "int":
        try:
            return int(raw)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for {key}: {raw!r} — expected int"
            )

    # --- float ---
    if target_type == "float":
        try:
            return float(raw)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for {key}: {raw!r} — expected float"
            )

    # --- bool ---
    if target_type == "bool":
        # Already a bool — pass through (e.g. from CLI argparse)
        if isinstance(raw, bool):
            return raw
        # String coercion, case-insensitive
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in _TRUTHY_STRINGS:
                return True
            if lowered in _FALSY_STRINGS:
                return False
        raise ConfigValidationError(
            f"Invalid value for {key}: {raw!r} — expected bool"
        )

    # --- enum ---
    if target_type == "enum":
        value_str = str(raw)
        allowed = schema_entry["allowed"]
        if value_str not in allowed:
            raise ConfigValidationError(
                f"Invalid value for {key}: {raw!r} — must be one of {allowed}"
            )
        return value_str

    # Fallback — should never be reached with a valid schema
    return raw


def validate_value(key: str, value: Any) -> Any:
    """Validate and coerce a single value for the given config key.

    Steps:
    1. Verify the key exists in _SCHEMA.
    2. Coerce the value to the declared type.
    3. Apply additional validation rules (e.g. non_empty).

    Args:
        key: The config key to validate against.
        value: The raw value to validate and coerce.

    Returns:
        The coerced and validated value.

    Raises:
        ConfigValidationError: If the key is unknown or validation fails.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: {key!r}")

    schema_entry = _SCHEMA[key]
    coerced = _coerce_value(key, value, schema_entry)

    # Post-coercion validation rules
    validation = schema_entry.get("validation")
    if validation == "non_empty":
        if not isinstance(coerced, str) or coerced.strip() == "":
            raise ConfigValidationError(
                f"Invalid value for {key}: {coerced!r} — must be non-empty"
            )

    if validation == "range":
        if not (schema_entry["min"] <= coerced <= schema_entry["max"]):
            raise ConfigValidationError(
                f"Invalid value for {key}: {coerced!r} — must be in range "
                f"[{schema_entry['min']}, {schema_entry['max']}]"
            )

    return coerced


def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources.

    Priority cascade (highest first):
        cli_args > env_vars > config_file > defaults

    Layers are applied in order from lowest to highest priority:
    1. Defaults from _SCHEMA
    2. JSON config file (only known keys; unknown keys ignored)
    3. Environment variables (mapped via env_var in _SCHEMA)
    4. CLI arguments (only known keys; None values skipped)

    After all layers are merged, every value is coerced and validated.

    Args:
        config_file: Path to a JSON config file, or None to skip.
        env_vars: Dict of environment variables (defaults to os.environ).
        cli_args: Dict of CLI-supplied values, or None to skip.

    Returns:
        A dict with all 10 config keys set to their final validated values.

    Raises:
        FileNotFoundError: If config_file does not exist.
        ConfigValidationError: If any value fails coercion or validation.
    """
    # Step 1 — defaults (lowest priority)
    result: dict[str, Any] = {}
    for key, entry in _SCHEMA.items():
        result[key] = entry["default"]

    # Step 2 — JSON config file overlay
    if config_file is not None:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
        except FileNotFoundError:
            raise
        except json.JSONDecodeError as e:
            raise ConfigValidationError(
                f"Invalid JSON in config file {config_file!r}: {e}"
            )

        if isinstance(file_data, dict):
            for key, value in file_data.items():
                if key in _SCHEMA:
                    result[key] = value  # raw — coerced in final pass

    # Step 3 — environment variables overlay
    if env_vars is None:
        env_vars = os.environ

    for key, entry in _SCHEMA.items():
        env_key = entry["env_var"]
        if env_key in env_vars:
            result[key] = env_vars[env_key]  # raw string — coerced in final pass

    # Step 4 — CLI args overlay (highest priority)
    if cli_args is not None:
        for key, value in cli_args.items():
            if key in _SCHEMA and value is not None:
                result[key] = value  # raw — coerced in final pass

    # Step 5 — coerce and validate every key in final result
    for key in list(result.keys()):
        result[key] = validate_value(key, result[key])

    return result


def get_schema() -> dict:
    """Return a deep copy of the full configuration schema.

    Returns:
        A dict mapping each config key to its schema entry (type, default,
        env_var, validation rules). Mutations to the returned dict will not
        affect the internal _SCHEMA.
    """
    return {key: dict(entry) for key, entry in _SCHEMA.items()}
