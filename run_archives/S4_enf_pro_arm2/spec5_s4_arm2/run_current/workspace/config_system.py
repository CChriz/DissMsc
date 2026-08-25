"""
Configuration system — loads, validates, and coerces configuration values
from multiple sources with a defined priority cascade.

Priority (highest first): CLI args > env vars > config file > defaults
"""

import json
import os


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigValidationError(ValueError):
    """Raised when a config value fails validation."""
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_BOOL_TRUE  = {"true", "1", "yes", "on"}
_BOOL_FALSE = {"false", "0", "no", "off"}


def _coerce_value(key, value, type_):
    """Coerce *value* to the target *type_*.

    Raises ConfigValidationError when coercion is impossible.
    """
    if type_ == "string":
        return str(value) if not isinstance(value, str) else value

    if type_ == "int":
        # bool is a subclass of int — guard against it
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} - not a valid integer"
            )

    if type_ == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.lower()
            if lowered in _BOOL_TRUE:
                return True
            if lowered in _BOOL_FALSE:
                return False
        if isinstance(value, int) and not isinstance(value, bool) and value in (0, 1):
            return bool(value)
        raise ConfigValidationError(
            f"Invalid value for '{key}': {value!r} - not a valid boolean"
        )

    if type_ == "enum":
        return str(value) if not isinstance(value, str) else value

    # Fallback — return as-is for unknown types
    return value


def _validate(key, value, type_, validation):
    """Validate *value* (already coerced) against the schema rules."""
    if type_ == "int":
        r = validation.get("range")
        if r is not None and not (r[0] <= value <= r[1]):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} - "
                f"must be in range [{r[0]}, {r[1]}]"
            )

    elif type_ == "string":
        if validation.get("non_empty") and (not isinstance(value, str) or value == ""):
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} - "
                f"must be a non-empty string"
            )

    elif type_ == "enum":
        allowed = validation.get("allowed", [])
        if value not in allowed:
            raise ConfigValidationError(
                f"Invalid value for '{key}': {value!r} - "
                f"must be one of {allowed}"
            )

    # bool — no extra validation required (coercion already handled)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_schema():
    """Return the full configuration schema as a dict.

    Each key maps to a spec dict with:
        type       — "string" | "int" | "bool" | "enum"
        default    — fallback value used when no source provides one
        env_var    — name of the environment variable to check
        validation — dict of validation rules (range, allowed, non_empty)
    """
    return {
        "host": {
            "type": "string",
            "default": "0.0.0.0",
            "env_var": "WEB_HOST",
            "validation": {"non_empty": True},
        },
        "port": {
            "type": "int",
            "default": 6155,
            "env_var": "WEB_PORT",
            "validation": {"range": [2048, 49151]},
        },
        "log_level": {
            "type": "enum",
            "default": "WARN",
            "env_var": "WEB_LOG_LEVEL",
            "validation": {"allowed": ["INFO", "WARN", "ERROR"]},
        },
        "request_timeout": {
            "type": "int",
            "default": 120,
            "env_var": "WEB_REQUEST_TIMEOUT",
            "validation": {"range": [1, 3600]},
        },
        "max_connections": {
            "type": "int",
            "default": 348,
            "env_var": "WEB_MAX_CONNECTIONS",
            "validation": {"range": [1, 1000]},
        },
        "debug_mode": {
            "type": "bool",
            "default": False,
            "env_var": "WEB_DEBUG",
            "validation": {},
        },
        "static_dir": {
            "type": "string",
            "default": "./static",
            "env_var": "WEB_STATIC_DIR",
            "validation": {"non_empty": True},
        },
        "cors_origins": {
            "type": "string",
            "default": "*",
            "env_var": "WEB_CORS_ORIGINS",
            "validation": {},
        },
        "keep_alive_timeout": {
            "type": "int",
            "default": 10,
            "env_var": "WEB_KEEP_ALIVE_TIMEOUT",
            "validation": {"range": [1, 300]},
        },
        "ssl_enabled": {
            "type": "bool",
            "default": False,
            "env_var": "WEB_SSL_ENABLED",
            "validation": {},
        },
    }


def validate_value(key, value):
    """Validate and coerce a single configuration value for *key*.

    Returns the coerced value.
    Raises ConfigValidationError on validation failure.
    Raises KeyError when *key* is unknown.
    """
    schema = get_schema()
    if key not in schema:
        raise KeyError(f"Unknown config key: {key!r}")

    spec = schema[key]
    coerced = _coerce_value(key, value, spec["type"])
    _validate(key, coerced, spec["type"], spec["validation"])
    return coerced


def load_config(config_file=None, env_vars=None, cli_args=None):
    """Load and validate configuration from all sources.

    Priority cascade (highest first):
        1. cli_args   — dict of key → value (optional)
        2. env_vars   — dict of key → value, defaults to os.environ
        3. config_file — path to a JSON file (optional)
        4. schema defaults — built-in fallbacks

    Raises FileNotFoundError when *config_file* points to a non-existent file.
    Raises ConfigValidationError when any value fails validation.
    """
    schema = get_schema()

    # ---- Layer 4: defaults ------------------------------------------------
    result = {key: spec["default"] for key, spec in schema.items()}

    # ---- Layer 3: JSON config file ----------------------------------------
    if config_file is not None:
        try:
            with open(config_file, "r") as f:
                file_config = json.load(f)
        except FileNotFoundError:
            raise  # re-raise as specified
        for key, val in file_config.items():
            if key in schema and val is not None:
                result[key] = val

    # ---- Layer 2: environment variables -----------------------------------
    if env_vars is None:
        env_vars = os.environ
    for key, spec in schema.items():
        env_val = env_vars.get(spec["env_var"])
        if env_val is not None:
            result[key] = env_val

    # ---- Layer 1: CLI arguments (highest priority) ------------------------
    if cli_args:
        for key, val in cli_args.items():
            if key in schema and val is not None:
                result[key] = val

    # ---- Validate & coerce every key -------------------------------------
    for key in schema:
        result[key] = validate_value(key, result[key])

    return result
