"""
Configuration system for the Web Service application.

Implements:
- ConfigValidationError: custom exception for validation failures
- load_config(): loads config from config file, env vars, and CLI args
- get_schema(): returns a deep copy of the full config schema
- validate_value(): validates and coerces a single config value
"""

import os
import json
import copy


# ============================================================
# Full Config Schema (10 keys)
# ============================================================

_SCHEMA = {
    "host": {
        "type": "string",
        "default": "0.0.0.0",
        "env_var": "WEB_HOST",
        "validate": "non_empty",
    },
    "port": {
        "type": "int",
        "default": 6155,
        "env_var": "WEB_PORT",
        "validate": "range",
        "range": [2048, 49151],
    },
    "log_level": {
        "type": "enum",
        "default": "WARN",
        "env_var": "WEB_LOG_LEVEL",
        "validate": "enum",
        "allowed": ["INFO", "WARN", "ERROR"],
    },
    "request_timeout": {
        "type": "int",
        "default": 120,
        "env_var": "WEB_REQUEST_TIMEOUT",
        "validate": "range",
        "range": [1, 3600],
    },
    "max_connections": {
        "type": "int",
        "default": 348,
        "env_var": "WEB_MAX_CONNECTIONS",
        "validate": "range",
        "range": [1, 1000],
    },
    "debug_mode": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_DEBUG",
        "validate": "bool",
    },
    "static_dir": {
        "type": "string",
        "default": "./static",
        "env_var": "WEB_STATIC_DIR",
        "validate": "non_empty",
    },
    "cors_origins": {
        "type": "string",
        "default": "*",
        "env_var": "WEB_CORS_ORIGINS",
        "validate": "any",
    },
    "keep_alive_timeout": {
        "type": "int",
        "default": 10,
        "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
        "validate": "range",
        "range": [1, 300],
    },
    "ssl_enabled": {
        "type": "bool",
        "default": False,
        "env_var": "WEB_SSL_ENABLED",
        "validate": "bool",
    },
}


# ============================================================
# Exception
# ============================================================

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ============================================================
# Internal: Type Coercion
# ============================================================

def _coerce_value(key: str, raw_value, spec: dict):
    """Coerce raw_value to the target type specified in spec.

    Raises ConfigValidationError on coercion failure.
    """
    target_type = spec["type"]

    # --- string ---
    if target_type == "string":
        if not isinstance(raw_value, str):
            raw_value = str(raw_value)
        return raw_value

    # --- int ---
    if target_type == "int":
        # bool is a subclass of int — must exclude it
        if isinstance(raw_value, bool):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — not a valid integer"
            )
        if isinstance(raw_value, int):
            return raw_value
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — not a valid integer"
            )

    # --- float ---
    if target_type == "float":
        if isinstance(raw_value, bool):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — not a valid float"
            )
        if isinstance(raw_value, float):
            return raw_value
        if isinstance(raw_value, int):
            return float(raw_value)
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — not a valid float"
            )

    # --- bool ---
    if target_type == "bool":
        # Already a Python bool
        if isinstance(raw_value, bool):
            return raw_value

        # String mapping (trimmed & lowercased)
        if isinstance(raw_value, str):
            trimmed = raw_value.strip().lower()
            if trimmed in ("true", "1", "yes", "on"):
                return True
            if trimmed in ("false", "0", "no", "off"):
                return False
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                "expected true/false/1/0/yes/no/on/off"
            )

        # Integer 1 / 0 (must exclude bool, already handled above)
        if isinstance(raw_value, int):
            if raw_value == 1:
                return True
            if raw_value == 0:
                return False

        # Anything else
        raise ConfigValidationError(
            f"Invalid value for '{key}': {raw_value!r} — "
            "expected true/false/1/0/yes/no/on/off"
        )

    # --- enum ---
    if target_type == "enum":
        if not isinstance(raw_value, str):
            raw_value = str(raw_value)
        if raw_value not in spec["allowed"]:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {raw_value!r} — "
                f"must be one of {spec['allowed']}"
            )
        return raw_value

    # Fallback (should not reach here)
    return raw_value


# ============================================================
# Internal: Validation
# ============================================================

def _validate_value(key: str, coerced_value, spec: dict) -> None:
    """Validate a coerced value against the spec's validation rule.

    Raises ConfigValidationError on validation failure.
    """
    validate_rule = spec.get("validate")

    if validate_rule == "non_empty":
        if coerced_value == "":
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced_value!r} — "
                "must be a non-empty string"
            )

    elif validate_rule == "range":
        min_val, max_val = spec["range"]
        if coerced_value < min_val or coerced_value > max_val:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced_value} — "
                f"must be in range [{min_val}, {max_val}]"
            )

    elif validate_rule == "enum":
        # Enum validation already handled in _coerce_value for enum type.
        # But if validate is "enum" and type is not enum, we re-check here.
        allowed = spec.get("allowed", [])
        if coerced_value not in allowed:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {coerced_value!r} — "
                f"must be one of {allowed}"
            )

    elif validate_rule == "bool":
        # Bool coercion already handled in _coerce_value.
        pass

    elif validate_rule == "any":
        # No validation
        pass


# ============================================================
# Public API: validate_value
# ============================================================

def validate_value(key: str, value) -> object:
    """Validate and coerce a single value for the given config key.

    Returns the coerced value.

    Raises ConfigValidationError if the key is unknown, or if coercion /
    validation fails.
    """
    if key not in _SCHEMA:
        raise ConfigValidationError(f"Unknown config key: {key!r}")

    spec = _SCHEMA[key]
    coerced = _coerce_value(key, value, spec)
    _validate_value(key, coerced, spec)
    return coerced


# ============================================================
# Public API: get_schema
# ============================================================

def get_schema() -> dict:
    """Return a deep copy of the full config schema."""
    return copy.deepcopy(_SCHEMA)


# ============================================================
# Public API: load_config
# ============================================================

def load_config(
    config_file: str | None = None,
    env_vars: dict | None = None,
    cli_args: dict | None = None,
) -> dict:
    """Load and validate configuration from all sources.

    Priority (highest first): cli_args > env_vars > config_file > defaults

    Args:
        config_file: Path to a JSON config file, or None to skip.
        env_vars: Dict of environment variables (default: os.environ).
        cli_args: Dict of CLI arguments, or None to skip.

    Returns:
        A dict with all config keys set to their final values.

    Raises:
        FileNotFoundError: If config_file does not exist.
        ConfigValidationError: If the config file contains invalid JSON
                                or any value fails validation.
    """
    # Step 1 — Initialize with defaults
    result = {}
    for key, spec in _SCHEMA.items():
        result[key] = spec["default"]

    # Step 2 — Load config file (priority 3)
    if config_file is not None:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                file_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(
                f"Invalid JSON in config file '{config_file}': {e}"
            )

        for key, raw in file_data.items():
            if key in _SCHEMA:
                spec = _SCHEMA[key]
                coerced = _coerce_value(key, raw, spec)
                _validate_value(key, coerced, spec)
                result[key] = coerced

    # Step 3 — Load environment variables (priority 2)
    if env_vars is None:
        env_vars = os.environ

    for key, spec in _SCHEMA.items():
        env_name = spec.get("env_var")
        if env_name and env_name in env_vars:
            raw = env_vars[env_name]
            coerced = _coerce_value(key, raw, spec)
            _validate_value(key, coerced, spec)
            result[key] = coerced

    # Step 4 — Load CLI args (priority 1)
    if cli_args:
        for key, raw in cli_args.items():
            if key in _SCHEMA:
                spec = _SCHEMA[key]
                coerced = _coerce_value(key, raw, spec)
                _validate_value(key, coerced, spec)
                result[key] = coerced

    # Step 5 — Return
    return result
